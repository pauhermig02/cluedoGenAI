# app.py
from __future__ import annotations

import json
import os
import sys
from html import escape, unescape
from typing import Dict, List, Optional
from datetime import datetime
import re
import signal
from dotenv import load_dotenv
import streamlit as st
import time
import random
import base64

if sys.platform == "win32":
    if not hasattr(signal, "SIGHUP"):
        signal.SIGHUP = signal.SIGTERM
        signal.SIGTSTP = signal.SIGTERM
        signal.SIGCONT = signal.SIGTERM

load_dotenv()  # Tiene en cuenta el archivo .env que contiene la API key

# ✅ Añadir la carpeta src al PYTHONPATH para que se vea cluedogenai
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))    # .../genAICluedo/cluedoGenAI
SRC_PATH = os.path.join(CURRENT_DIR, "src")                 # .../genAICluedo/cluedoGenAI/src
AUDIO_DIR = os.path.join(CURRENT_DIR, "assets", "audio")    # Carpeta con los mp3/wav

if SRC_PATH not in sys.path:
    # MUY IMPORTANTE: insertarlo al principio, antes de site-packages
    sys.path.insert(0, SRC_PATH)

from cluedogenai.crew import Cluedogenai  # noqa: E402

TOTAL_QUESTIONS = 10
MAX_TURNS_IN_SUMMARY = 3
CREW_TOPIC = "AI Murder Mystery"


# =========================
#  CREW HELPERS
# =========================

def _extract_json_object_with_key(text: str, required_key: str) -> Optional[dict]:
    """Busca y parsea el PRIMER objeto JSON válido que contenga required_key."""
    if not text:
        return None

    cleaned = text.replace("```json", "").replace("```", "")
    dec = json.JSONDecoder()

    for m in re.finditer(r"\{", cleaned):
        start = m.start()
        try:
            obj, _ = dec.raw_decode(cleaned[start:])
            if isinstance(obj, dict) and required_key in obj:
                return obj
        except Exception:
            continue
    return None


def _strip_html_tags(text: str) -> str:
    """Elimina cualquier etiqueta HTML básica de un string."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text.strip()


def _safe_get_task_raw(task_obj) -> Optional[str]:
    """
    Intenta extraer un string "crudo" de un TaskOutput de CrewAI,
    probando atributos comunes (raw, output, value, etc.).
    """
    if task_obj is None:
        return None
    for attr in ("raw", "output", "value", "result", "content"):
        if hasattr(task_obj, attr):
            val = getattr(task_obj, attr)
            if isinstance(val, str) and val.strip():
                return val
    s = str(task_obj)
    return s if s.strip() else None

def _clean_generated_images() -> None:
    """Elimina todos los archivos .png/.jpg de la carpeta generated_images."""
    images_dir_abs = os.path.join(SRC_PATH, "cluedogenai", "generated_images")
    if not os.path.exists(images_dir_abs):
        return
    
    print(f"Cleaning old images in: {images_dir_abs}")
    for fname in os.listdir(images_dir_abs):
        if fname.lower().endswith((".png", ".jpg", ".jpeg")):
            try:
                os.path.join(images_dir_abs, fname)
                os.remove(os.path.join(images_dir_abs, fname))
            except Exception as e:
                print(f"Could not delete {fname}: {e}")


def generate_case_with_crew() -> Dict:

    # Delete images from previous games
    _clean_generated_images()

    """
    Usa la Crew para generar escena y sospechosos.
    Busca las imágenes directamente en el disco.
    """
    base_case = {
        "victim": "Unknown Victim",
        "time": "Sometime past midnight",
        "place": "An almost empty tech office",
        "cause": "Suspicious accident with smart equipment",
        "context": "A storm hits the city. Backup power keeps the systems barely alive."
    }

    game_state = json.dumps(base_case, ensure_ascii=False)
    player_action = "We are starting the game. Design the opening scene and the full cast of suspects."

    crew_inputs = {
        "topic": CREW_TOPIC,
        "current_year": str(datetime.now().year),
        "game_state": game_state,
        "player_action": player_action,
    }

    crew = Cluedogenai().setup_crew()

    try:
        # ✅ FIX: Avoids telemetry timeout implicitly by env vars above
        result = crew.kickoff(inputs=crew_inputs)
    except Exception as e:
        raise RuntimeError(f"Error calling CrewAI: {e}") from e

    def _read_json_artifact(rel_path: str, required_key: str) -> Optional[dict]:
        abs_path = os.path.join(CURRENT_DIR, rel_path)
        if not os.path.exists(abs_path):
            return None
        with open(abs_path, "r", encoding="utf-8") as f:
            txt = f.read().strip()
        return _extract_json_object_with_key(txt, required_key)


    # después del kickoff:
    scene_blueprint_json = _read_json_artifact("artifacts/scene_blueprint.json", "scene_id")
    characters_json      = _read_json_artifact("artifacts/characters.json", "suspects")
    vision_json          = _read_json_artifact("artifacts/suspect_images.json", "suspect_images")

    # Save to session
    if scene_blueprint_json: st.session_state.scene_blueprint = scene_blueprint_json
    if characters_json: st.session_state.characters = characters_json

    # --- ENRICH CASE DETAILS (from scene_blueprint.json) ---
    if scene_blueprint_json:
        # Location -> place
        loc = scene_blueprint_json.get("location")
        if loc:
            base_case["place"] = loc

        # Summary -> context
        summary = scene_blueprint_json.get("summary")
        if summary:
            base_case["context"] = summary

        # Victim name from present_characters
        # ✅ Victim name: now comes explicitly from the blueprint
        vname = scene_blueprint_json.get("victim_name")
        if isinstance(vname, str) and vname.strip():
            base_case["victim"] = vname.strip()


        # Time (scene blueprint doesn’t always include a "time" field)
        # Derive a nicer one from summary if possible
        if summary:
            low = summary.lower()
            if "storm" in low or "violent storm" in low:
                base_case["time"] = "Late night during a violent storm"
            elif "midnight" in low:
                base_case["time"] = "Just after midnight"

        # Cause from visible clues (if available)
        clues = scene_blueprint_json.get("visible_clues") or []
        cause = None
        joined = " ".join([str(c) for c in clues]).lower()
        if "electrocution" in joined:
            cause = "Severe electrocution near damaged server equipment"
        elif "impact" in joined or "trauma" in joined:
            cause = "Blunt impact trauma during a staged 'accident'"
        if cause:
            base_case["cause"] = cause

    # --- PROCESS SUSPECTS & FIND IMAGES ---
    if not characters_json or "suspects" not in characters_json:
        # Fallback: intenta extraer characters_json desde result/tasks_output o str(result)
        tasks_out = getattr(result, "tasks_output", None)
        if isinstance(tasks_out, list):
            for t in tasks_out:
                raw = _safe_get_task_raw(t) or ""
                obj = _extract_json_object_with_key(str(result), "suspects")

                if obj:
                    characters_json = obj
                    break



        if not characters_json or "suspects" not in characters_json:
            # Último fallback: parsear el string completo del result
            obj = _extract_json_object_with_key(str(result), "suspects")
            if obj:
                characters_json = obj


    if not characters_json or "suspects" not in characters_json:
        raise RuntimeError("Invalid characters JSON")

    suspects_raw = characters_json["suspects"]

    # 1) Guilty
    guilty_name = characters_json.get("guilty_name")
    if not guilty_name:
        for s in suspects_raw:
            if s.get("guilty") is True:
                guilty_name = s.get("name")
                break

            

    # 2) Vision output (preferir mapping exacto de suspect_images)
    vision_images = {}
    vision_failed = {}
    if isinstance(vision_json, dict):
        vision_images = vision_json.get("suspect_images") or {}
        vision_failed = vision_json.get("failed") or {}

    # Fallback: si no hay artifacts, intentar sacar suspect_images del result final
    if not vision_images:
        obj = _extract_json_object_with_key(str(result), "suspect_images")
        if obj and isinstance(obj.get("suspect_images"), dict):
            vision_images = obj.get("suspect_images") or {}
            vision_failed = obj.get("failed") or {}


    # 3) Scan folder como fallback final (si tampoco vino mapping)
    images_dir_abs = os.path.join(SRC_PATH, "cluedogenai", "generated_images")
    available_files = os.listdir(images_dir_abs) if os.path.isdir(images_dir_abs) else []
    print(f"📂 Scanning for images in: {images_dir_abs}")
    print(f"📂 Files found: {available_files}")

    suspects: List[Dict] = []

    # Rastrear imágenes ya asignadas para evitar repetir la misma imagen en dos sospechosos
    assigned_images = set()

    for s in suspects_raw:
        name = s.get("name", "Unknown")

        # 1. Definir base del sospechoso
        suspect_dict = {
            "name": name,
            "role": s.get("role", ""),
            "personality": s.get("personality", ""),
            "secret": s.get("secret") or s.get("secret_motivation", ""),
            "guilty": (name == guilty_name),
            "image_path": None  # <--- IMPORTANTE: Empezamos siempre como None
        }

        # 2. Intentar buscar imagen
        found_path = None

        # A) Intentar vía JSON directo (output de la crew)
        img_candidate = vision_images.get(name)
        if img_candidate:
            # Validar que el archivo existe físicamente (por si hubo error 429 al crearlo)
            abs_path = os.path.join(CURRENT_DIR, img_candidate)
            if os.path.exists(abs_path) and abs_path not in assigned_images:
                found_path = img_candidate
                print(f"✅ Image Linked via JSON: {name} -> {found_path}")

        # B) Fallback: Escanear carpeta si no se encontró en JSON
        if not found_path:
            safe_name_prefix = str(name).replace(" ", "_")
            # Buscamos en los archivos disponibles
            for fname in available_files:
                # Verificamos prefijo y que no sea una imagen ya usada
                f_abs = os.path.join(images_dir_abs, fname)
                if (fname.lower().startswith(safe_name_prefix.lower()) 
                    and fname.lower().endswith(".png")
                    and f_abs not in assigned_images):
                    
                    found_path = os.path.join("src", "cluedogenai", "generated_images", fname)
                    print(f"✅ Image Linked via Scan: {name} -> {found_path}")
                    break

        # 3. Asignar imagen si se encontró
        if found_path:
            suspect_dict["image_path"] = found_path
            # Marcamos esta ruta absoluta como usada para que nadie más la coja
            abs_p = os.path.join(CURRENT_DIR, found_path)
            assigned_images.add(abs_p)
        else:
            print(f"❌ No image found for: {name} (Quota exceeded or generation failed)")

        suspects.append(suspect_dict)

    case = dict(base_case)
    case["suspects"] = suspects
    case["guilty_name"] = guilty_name

    return case



def call_crew_for_answer(
    case: Dict,
    suspect_name: str,
    history: List[Dict],
    question: str,
) -> str:
    """
    Usa la Crew para generar la respuesta del sospechoso.
    """
    system_prompt = build_system_prompt(case, suspect_name)
    user_prompt = build_user_prompt(suspect_name, history, question)

    scene_blueprint = st.session_state.get("scene_blueprint")
    characters = st.session_state.get("characters")

    crew_inputs = {
        "topic": CREW_TOPIC,
        "current_year": str(datetime.now().year),
        "game_state": system_prompt,
        "player_action": user_prompt,
        "scene_blueprint": json.dumps(scene_blueprint, ensure_ascii=False) if scene_blueprint else "",
        "characters": json.dumps(characters, ensure_ascii=False) if characters else "",
    }

    try:
        crew = Cluedogenai().dialogue_crew()
        result = crew.kickoff(inputs=crew_inputs)

        tasks_out = getattr(result, "tasks_output", None) or getattr(result, "raw", None)
        data = None

        if isinstance(tasks_out, list):
            for t in tasks_out:
                raw = _safe_get_task_raw(t)
                if not raw:
                    continue
                candidate = _extract_json_object_with_key(raw, "spoken_text")
                if candidate:
                    data = candidate
                    break


        elif isinstance(tasks_out, dict):
            t = tasks_out.get("generate_suspect_dialogue")
            if t is not None:
                raw = _safe_get_task_raw(t)
                data = _extract_json_object_with_key(raw, "spoken_text")


        if isinstance(data, dict):
            spoken = data.get("spoken_text") or data.get("answer") or data.get("text")
            if spoken:
                return spoken.strip()

        raw_fallback = str(result)
        data_fb = _extract_json_object_with_key(raw_fallback, "spoken_text")
        if isinstance(data_fb, dict):
            spoken_fb = data_fb.get("spoken_text") or data_fb.get("answer") or data_fb.get("text")
            if spoken_fb:
                return spoken_fb.strip()

        answer_text = raw_fallback.strip()
        if len(answer_text) > 400:
            answer_text = answer_text[:400] + "..."
        return answer_text

    except Exception as e:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "Quota exceeded" in msg:
            return (
                "The overhead lights flicker and the network icon turns red. "
                "«Systems are throttled… you won’t get more out of me right now,» "
                "the suspect says, dodging your question."
            )
        return (
            "The suspect just stares back at you. "
            "Something in the system glitched and they refuse to answer."
        )


# =========================
#  AUDIO HELPERS (sin music_manager)
# =========================

def _scan_audio_assets() -> Dict[str, List[str]]:
    """
    Escanea assets/audio y devuelve un dict:
      {
        "ambient": [...],
        "question": [...],
        "accuse": [...],
        "ending": [...],
      }
    Clasifica por nombre de archivo (Ambient_, Question_, Accuse_, Ending_).
    """
    tracks = {"ambient": [], "question": [], "accuse": [], "ending": []}
    if not os.path.isdir(AUDIO_DIR):
        print(f"[MUSIC] Audio dir not found: {AUDIO_DIR}")
        return tracks

    for fname in os.listdir(AUDIO_DIR):
        fpath = os.path.join(AUDIO_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        lower = fname.lower()
        if not (lower.endswith(".mp3") or lower.endswith(".wav")):
            continue

        if lower.startswith("ambient_"):
            tracks["ambient"].append(fpath)
        elif lower.startswith("question_"):
            tracks["question"].append(fpath)
        elif lower.startswith("accuse_"):
            tracks["accuse"].append(fpath)
        elif lower.startswith("ending_"):
            tracks["ending"].append(fpath)

    print("[MUSIC] Scanned tracks:", tracks)
    return tracks


def trigger_question_sound_local() -> None:
    tracks = st.session_state.get("music_tracks", {})
    pool = tracks.get("question", []) or []
    if not pool:
        print("No question SFX available")
        return
    path = random.choice(pool)
    try:
        with open(path, "rb") as f:
            st.session_state.last_sfx_bytes = f.read()
            st.session_state._sfx_key = f"sfx_{int(time.time() * 1000)}"
    except Exception:
        st.session_state.last_sfx_bytes = None


def trigger_accusation_sound_local() -> None:
    tracks = st.session_state.get("music_tracks", {})
    pool = tracks.get("accuse", []) or []
    if pool:
        path = random.choice(pool)
        try:
            with open(path, "rb") as f:
                st.session_state.last_sfx_bytes = f.read()
                st.session_state._sfx_key = f"sfx_{int(time.time() * 1000)}"
        except Exception:
            st.session_state.last_sfx_bytes = None
    else:
        print("No accusation SFX available")

    ending_pool = tracks.get("ending", []) or []
    if ending_pool:
        chosen_ending = random.choice(ending_pool)
        try:
            st.session_state._pending_ending_data_url = file_to_data_url(chosen_ending)
            st.session_state._pending_switch_to_ending = True
        except Exception:
            st.session_state._pending_ending_data_url = None
            st.session_state._pending_switch_to_ending = False
    else:
        st.session_state._pending_switch_to_ending = False


def file_to_data_url(path: str) -> Optional[str]:
    """Lee un fichero audio y devuelve una data URL 'data:audio/mp3;base64,...'."""
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            b = f.read()
        # Asumimos mp3; Chrome lo reproduce igual si es wav pero podrías ajustar el mime
        return "data:audio/mp3;base64," + base64.b64encode(b).decode()
    except Exception:
        return None


def toggle_music_enabled() -> None:
    """
    Alterna st.session_state.music_enabled entre True/False.
    Si activamos música y no hay bg_path calculado, inicializamos audio.
    """
    cur = st.session_state.get("music_enabled", False)
    st.session_state.music_enabled = not cur

    if st.session_state.music_enabled and "music_tracks" not in st.session_state:
        try:
            init_music_state_local()
        except Exception:
            pass

    if st.session_state.get("music_enabled", False):
        bg_path = st.session_state.get("bg_path")
        if bg_path and not st.session_state.get("bg_data_url"):
            try:
                st.session_state.bg_data_url = file_to_data_url(bg_path)
            except Exception:
                st.session_state.bg_data_url = None


# =========================
#  GAME STATE & LOGIC
# =========================

def init_music_state_local() -> None:
    """Inicializa pistas de audio a partir de assets/audio."""
    if "music_tracks" in st.session_state:
        return

    tracks = _scan_audio_assets()
    st.session_state.music_tracks = tracks
    st.session_state.music_mode = "ambient"

    bg_path = None
    ambient_list = tracks.get("ambient", []) or []
    if ambient_list:
        bg_path = random.choice(ambient_list)
    st.session_state.bg_path = bg_path
    st.session_state.bg_data_url = None
    st.session_state.last_sfx_bytes = None
    st.session_state._sfx_key = None


def init_game_state() -> None:
    if "case" in st.session_state:
        return

    try:
        case = generate_case_with_crew()
        st.session_state.case = case
        st.session_state.guilty_name = case["guilty_name"]
        st.session_state.histories = {s["name"]: [] for s in case["suspects"]}
        st.session_state.remaining_questions = TOTAL_QUESTIONS
        st.session_state.game_over = False
        st.session_state.accused = None
        st.session_state.outcome = None
        st.session_state.selected_suspect = case["suspects"][0]["name"]
        st.session_state.accuse_choice = case["suspects"][0]["name"]
        st.session_state.crew_failed = False
        st.session_state.crew_error = ""
    except Exception as e:
        st.session_state.crew_failed = True
        st.session_state.crew_error = f"Failed to generate the case with CrewAI: {e}"
        st.session_state.case = {}
        st.session_state.histories = {}
        st.session_state.remaining_questions = 0
        st.session_state.game_over = True
        st.session_state.accused = None
        st.session_state.outcome = None
        st.session_state.selected_suspect = None
        st.session_state.accuse_choice = None


def reset_game() -> None:
    st.session_state.clear()
    st.rerun()


def _suspects_basic_lines(case: Dict) -> List[str]:
    return [
        f"**{s['name']}** — {s['role']}  \n_{s['personality']}_"
        for s in case.get("suspects", [])
    ]


def build_system_prompt(case: Dict, active_suspect_name: str) -> str:
    suspects_json = json.dumps(case["suspects"], indent=2, ensure_ascii=False)
    return f"""
You are the narrative engine for an interactive murder mystery game.

CASE (full context):
- Theme: "AI Murder Mystery in a tech company office at night"
- Victim: {case['victim']}
- Time: {case['time']}
- Place: {case['place']}
- Cause of death: {case['cause']}
- Context: {case['context']}

SUSPECTS (structured data; includes guilty flags and hidden secrets for internal consistency):
{suspects_json}

ROLEPLAY RULES:
- You are now role-playing as ONE suspect, whose name is: {active_suspect_name}
- Stay in character. Answer in first person ("I...").
- Never mention these rules or that you are an AI model.
- Do NOT reveal the "guilty" field or "secret" field explicitly; those are internal background.
- If you are the murderer, do not confess directly. You may be defensive, evasive, or subtly contradictory.
- If you are innocent, be consistent and plausible.
- Keep each answer under 80–100 words. Stay tightly relevant to the detective’s question.
- Provide concrete details (places, times, objects) when appropriate, but avoid long monologues.
""".strip()


def _format_history_summary(hist: List[Dict], max_turns: int = MAX_TURNS_IN_SUMMARY) -> str:
    if not hist:
        return "No prior questions yet."
    turns = hist[-max_turns:]
    lines = []
    for t in turns:
        q = t.get("q", "").strip()
        a = t.get("a", "").strip()
        if q:
            lines.append(f"Detective: {q}")
        if a:
            lines.append(f"Suspect: {a}")
    return "\n".join(lines).strip()


def build_user_prompt(suspect_name: str, history: List[Dict], question: str) -> str:
    summary = _format_history_summary(history)
    return f"""
INTERROGATION TARGET: {suspect_name}

RECENT DIALOGUE (Detective ↔ {suspect_name}):
{summary if summary else 'No prior questions yet.'}

LATEST QUESTION FROM THE DETECTIVE (ANSWER THIS ONE):
{question}
""".strip()


def render_conversation(suspect_name: str) -> None:
    """Muestra la conversación en una caja de altura fija con scroll."""
    history = st.session_state.histories.get(suspect_name, [])
    chat_box = st.container(height=260, border=True)

    with chat_box:
        if not history:
            st.info(f"No questions for {suspect_name} yet. Ask something sharp.")
            return

        for turn in history:
            q = (turn.get("q") or "").strip()
            a = (turn.get("a") or "").strip()

            if q:
                with st.chat_message("user", avatar="🕵️"):
                    st.markdown(q)

            if a:
                with st.chat_message("assistant", avatar="🧩"):
                    st.markdown(a)


def handle_question_submit(suspect_name: str, question: str, disabled: bool) -> None:
    q = (question or "").strip()
    if not q:
        return
    if disabled:
        st.warning("CrewAI is currently unavailable; you cannot ask more questions.")
        return
    if st.session_state.game_over:
        st.info("The case is closed. Start a new game to ask more questions.")
        return
    if st.session_state.remaining_questions <= 0:
        st.warning("No questions left — you must accuse someone.")
        return

    case = st.session_state.case
    history = st.session_state.histories[suspect_name]

    st.session_state.remaining_questions -= 1

    with st.spinner(f"{suspect_name} is thinking…"):
        answer = call_crew_for_answer(case, suspect_name, history, q)

    answer = unescape(answer or "")
    answer = _strip_html_tags(answer)

    history.append({"q": q, "a": answer})

    try:
        trigger_question_sound_local()
    except Exception:
        print("Error triggering question sound")

    if st.session_state.remaining_questions <= 0:
        st.toast("No questions left. Time to accuse someone.", icon="⚖️")


def _generate_epilogue(case: Dict, accused_name: str, won: bool, guilty_name: str) -> str:
    if won:
        return (
            f"You lay out the last contradiction, and the room goes quiet.\n\n"
            f"{guilty_name} stops arguing and starts calculating. The storm outside fades, "
            "but the weight of the evidence doesn’t. Logs, timelines — "
            "all of it lines up in a single, sharp line pointing at them.\n\n"
            "Security walks them out. The office hums back to life, one monitor at a time."
        )
    else:
        return (
            f"You point the finger at {accused_name}, and the room tenses. "
            f"For a moment it almost fits — almost.\n\n"
            f"But the loose ends remain. Somewhere in the logs, in the access patterns, "
            f"in the off-by-one timestamp, {guilty_name} slips away clean.\n\n"
            "The storm passes. The case closes on paper, but not in your head."
        )


def handle_accusation(accused_name: str, disabled: bool) -> None:
    if disabled:
        st.warning("CrewAI is currently unavailable; you cannot close the case.")
        return
    if st.session_state.game_over:
        return

    case = st.session_state.case
    guilty_name = st.session_state.guilty_name

    try:
        trigger_accusation_sound_local()
    except Exception:
        pass

    st.session_state.accused = accused_name
    won = accused_name == guilty_name
    epilogue = _generate_epilogue(case, accused_name, won, guilty_name)

    st.session_state.outcome = {
        "won": won,
        "accused": accused_name,
        "guilty": guilty_name,
        "epilogue": epilogue,
    }
    st.session_state.game_over = True


# =========================
#  AUDIO RENDER
# =========================

def bytes_to_data_url(b: bytes) -> Optional[str]:
    if not b:
        return None
    try:
        return "data:audio/mp3;base64," + base64.b64encode(b).decode()
    except Exception:
        return None


def render_music_player_local() -> None:
    """
    Renderiza background y reproduce SFX usando autoplay nativo HTML.
    """
    if not st.session_state.get("music_enabled", False):
        return

    # --- BACKGROUND AUDIO ---
    bg_data_url = st.session_state.get("bg_data_url")
    bg_path = st.session_state.get("bg_path")

    if not bg_data_url and bg_path:
        bg_data_url = file_to_data_url(bg_path)
        st.session_state.bg_data_url = bg_data_url

    if bg_data_url:
        html_bg = f"""
        <audio id="bg_audio" src="{bg_data_url}" loop autoplay
               style="width:100%; margin-bottom: 6px;">
        </audio>
        """
        st.markdown(html_bg, unsafe_allow_html=True)

    # --- SFX AUDIO ---
    sfx_bytes = st.session_state.get("last_sfx_bytes")
    if sfx_bytes:
        sfx_data_url = bytes_to_data_url(sfx_bytes)
        if sfx_data_url:
            sfx_id = f"sfx_{int(time.time() * 1000)}"
            html_sfx = f"""
            <audio id="{sfx_id}" src="{sfx_data_url}" autoplay="true" style="display:none;"></audio>
            <script>
                (function() {{
                    var bg = document.getElementById("bg_audio");
                    var sfx = document.getElementById("{sfx_id}");
                    if(bg && sfx) {{
                        var originalVol = bg.volume;
                        bg.volume = 0.2;
                        sfx.onended = function() {{
                            bg.volume = originalVol;
                        }};
                    }}
                }})();
            </script>
            """
            st.markdown(html_sfx, unsafe_allow_html=True)

        st.session_state.last_sfx_bytes = None
        st.session_state._sfx_key = None


# =========================
#  STREAMLIT RENDER
# =========================

def render_game() -> None:
    """Dibuja todo el juego en Streamlit (full width, sin sidebar)."""
    init_game_state()

    crew_failed = st.session_state.get("crew_failed", False)
    disabled = crew_failed

    # ✅ CSS: usa toda la pantalla, reduce padding vertical/lateral
    st.markdown(
        """
        <style>
          /* usa todo el ancho real */
          .block-container {
            max-width: 100% !important;
            padding-left: 1.0rem !important;
            padding-right: 1.0rem !important;
            padding-top: 0.6rem !important;
            padding-bottom: 0.6rem !important;
          }
          /* reduce espacios entre widgets */
          div[data-testid="stVerticalBlock"] > div { gap: 0.55rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if crew_failed:
        st.markdown(
            """
            <div style="display:flex; align-items:baseline; gap:12px;">
              <h1 style="margin:0;">AI Murder Mystery</h1>
              <div style="opacity:0.75; font-size:14px;">CrewAI failed to generate the case.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.error(st.session_state.get("crew_error", "Unknown error while calling CrewAI."))
        st.button("🔄 Retry generating case", on_click=reset_game)
        return

    # Inicializar música
    init_music_state_local()
    if "music_enabled" not in st.session_state:
        st.session_state.music_enabled = False

    case = st.session_state.case
    suspect_names = [s["name"] for s in case["suspects"]]

    # =========================
    # HEADER compacto (1 fila)
    # =========================
    h1, h2, h3, h4 = st.columns([2.2, 0.9, 0.9, 0.9], gap="small")
    with h1:
        st.markdown(
            """
            <div style="display:flex; align-items:baseline; gap:12px;">
              <h1 style="margin:0;">AI Murder Mystery</h1>
              <div style="opacity:0.75; font-size:14px;">
                Interrogate · Observe · Accuse
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with h2:
        st.metric("Questions", st.session_state.remaining_questions)
    with h3:
        label = "🔊 Music on" if not st.session_state.music_enabled else "🔇 Music off"
        st.button(label, on_click=toggle_music_enabled, use_container_width=True)
    with h4:
        st.button("🔄 New game", on_click=reset_game, use_container_width=True)

    render_music_player_local()

    # =========================
    # LAYOUT PRINCIPAL: 3 columnas
    # =========================
    col_case, col_interrogation, col_right = st.columns(
        [1.15, 2.4, 1.15],
        gap="small",
        vertical_alignment="top",
    )

    # -------- LEFT: Case + Suspects en tabs (no crece en alto) --------
    with col_case:
        tabs = st.tabs(["Case", "Suspects"])

        with tabs[0]:
            st.markdown("### Case")
            victim = escape(case.get("victim", "Unknown victim"))
            time_ = escape(case.get("time", "Unknown time"))
            place = escape(case.get("place", "Unknown place"))
            cause = escape(case.get("cause", "Unknown cause"))
            ctx = case.get("context", "") or ""

            st.markdown(
                f"""
- **Victim:** {victim}
- **Time:** {time_}
- **Place:** {place}
- **Cause:** {cause}
                """.strip()
            )

            # Context con scroll interno (no empuja la página)
            with st.container(height=160, border=True):
                st.caption(ctx)

        with tabs[1]:
            st.markdown("### Suspects")
            with st.container(height=360, border=True):
                for s in case.get("suspects", []):
                    st.markdown(f"**{s['name']}** — {s['role']}")
                    st.caption(s.get("personality", ""))

    # -------- CENTER: Interrogation --------
    with col_interrogation:
        st.markdown("### Interrogation")

        selected = st.selectbox(
            "Choose a suspect",
            suspect_names,
            key="selected_suspect",
            disabled=disabled,
        )

        s_map = {s["name"]: s for s in case["suspects"]}
        s = s_map[selected]

        # Perfil + imagen (compacto)
        prof_col, img_col = st.columns([1.6, 1.0], gap="small")
        with prof_col:
            st.markdown(
                f"""
                <div style="border:1px solid rgba(0,0,0,0.10); border-radius:16px;
                            padding:10px 12px; background:#fff;">
                  <div style="font-weight:800; font-size:16px;">{escape(s['name'])}</div>
                  <div style="opacity:0.85; font-size:13px;">
                    {escape(s.get('role',''))}<br/>
                    <span style="opacity:0.8;">{escape(s.get('personality',''))}</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with img_col:
            img_rel = s.get("image_path")
            image_found = False
            
            if img_rel:
                abs_path = img_rel if os.path.isabs(img_rel) else os.path.join(CURRENT_DIR, img_rel)
                if os.path.exists(abs_path):
                    st.image(abs_path, width=240)
                    image_found = True
            
            # FALLBACK: Si no se generó imagen (por error o filtro de seguridad)
            if not image_found:
                # Usamos un servicio de placeholders con las iniciales del sospechoso
                initials = "".join([n[0] for n in s['name'].split()[:2]]).upper()
                # Un color gris oscuro misterioso (333333) con texto claro
                placeholder_url = f"https://placehold.co/400x400/333333/DDDDDD/png?text={initials}&font=playfair-display"
                
                st.image(placeholder_url, width=240, caption="Identity obscured")
                # Opcional: Mostrar un mensaje pequeño explicando por qué
                #st.caption("Image unavailable (Security redacted)")

        st.markdown("#### Conversation")
        render_conversation(selected)

        can_ask = (
            (not st.session_state.game_over)
            and (st.session_state.remaining_questions > 0)
            and (not disabled)
        )

        if st.session_state.remaining_questions <= 0 and not st.session_state.game_over:
            st.warning("You are out of questions. Make your accusation on the right.")

        user_q = st.chat_input("Ask a question…", disabled=not can_ask)
        if user_q is not None:
            handle_question_submit(selected, user_q, disabled=disabled)
            st.rerun()

    # -------- RIGHT: Accuse & Outcome (compacto) --------
    with col_right:
        st.markdown("### Accuse")

        accuse_disabled = disabled or st.session_state.game_over
        st.selectbox(
            "Accuse one suspect",
            suspect_names,
            key="accuse_choice",
            disabled=accuse_disabled,
        )

        if st.button("⚖️ Accuse now", disabled=accuse_disabled, use_container_width=True):
            handle_accusation(st.session_state.accuse_choice, disabled=disabled)
            st.rerun()

        st.markdown("---")

        # Resultado con scroll interno para no empujar la pantalla
        with st.container(height=260, border=True):
            if st.session_state.outcome:
                out = st.session_state.outcome
                if out["won"]:
                    st.success(f"Correct. **{out['accused']}** is the murderer.")
                else:
                    st.error(
                        f"Wrong. You accused **{out['accused']}** — "
                        f"the real murderer was **{out['guilty']}**."
                    )
                st.write(out["epilogue"])
            elif st.session_state.game_over:
                st.info("Case closed. Reset to play again.")
            
        with st.expander("Tips", expanded=False):
            st.markdown(
                """
- Ask about **timestamps**, **locations**, and **what they touched**.
- Look for **subtle contradictions**: wrong sequence, wrong room, wrong system.
                """
            )
 


def main() -> None:
    st.set_page_config(page_title="AI Murder Mystery", page_icon="🕵️", layout="wide")
    render_game()


if __name__ == "__main__":
    main()
