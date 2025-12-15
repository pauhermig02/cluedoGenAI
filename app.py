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
import copy
from typing import Any
import traceback


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

ARTIFACTS_DIR = os.path.join(CURRENT_DIR, "artifacts")
ARTIFACT_FILES = [
    "scene_blueprint.json",
    "characters.json",
    "suspect_images.json",
    "solution.json",
]


from cluedogenai.crew import Cluedogenai  # noqa: E402

TOTAL_QUESTIONS = 10
MAX_TURNS_IN_SUMMARY = 3
CREW_TOPIC = "AI Murder Mystery"


# =========================
#  CREW HELPERS
# =========================

def _clean_artifacts() -> None:
    if not os.path.isdir(ARTIFACTS_DIR):
        return
    for fname in ARTIFACT_FILES:
        fpath = os.path.join(ARTIFACTS_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception as e:
                print(f"Could not delete artifact {fname}: {e}")


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


def sanitize_characters_for_dialogue(
    characters: Optional[Dict[str, Any]],
    active_suspect: str,
    *,
    redact_other_secrets: bool = True,
) -> Dict[str, Any]:
    """
    Returns a copy of `characters` safe to send to the dialogue LLM:
    - removes guilty flags + guilty_name
    - optionally removes other suspects' secret_motivation (keep only active suspect secret)
    """
    if not isinstance(characters, dict):
        return {}

    c = copy.deepcopy(characters)

    # Top-level spoiler keys
    c.pop("guilty_name", None)
    c.pop("murderer", None)
    c.pop("solution", None)
    c.pop("case_solution", None)
    c.pop("truth", None)
    c.pop("truth_summary", None)


    suspects = c.get("suspects")
    if not isinstance(suspects, list):
        return c

    for s in suspects:
        if not isinstance(s, dict):
            continue

        # Per-suspect spoiler keys
        s.pop("guilty", None)
        s.pop("is_guilty", None)
        s.pop("culpable", None)

        # Optional: don't let Ben know Maya's secret, etc.
        if redact_other_secrets and s.get("name") != active_suspect:
            s.pop("secret_motivation", None)
            s.pop("secret", None)

    return c


def sanitize_scene_blueprint_for_dialogue(
    scene_blueprint: Optional[Dict[str, Any]],
    active_suspect: str,
) -> Dict[str, Any]:
    """
    Returns a copy safe-ish for dialogue.
    Not strictly necessary, but helps consistency:
    - ensures the active suspect can be "present" without rewriting your artifacts.
    """
    if not isinstance(scene_blueprint, dict):
        return {}

    sb = copy.deepcopy(scene_blueprint)

    present = sb.get("present_characters")
    if isinstance(present, list):
        if active_suspect not in present:
            present.append(active_suspect)

    return sb


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
                os.remove(os.path.join(images_dir_abs, fname))
            except Exception as e:
                print(f"Could not delete {fname}: {e}")


def generate_case_with_crew() -> Dict:

    # Delete images from previous games
    _clean_generated_images()
    _clean_artifacts()

    """
    Usa la Crew para generar escena y sospechosos.
    Busca las imágenes directamente en el disco.
    """
    base_case = {
        "victim": "Unknown Victim",
        "victim_role": "Unknown role",
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

    try:
        crew = Cluedogenai().setup_crew()
    except Exception as e:
        raise RuntimeError("setup_crew() crashed:\n" + traceback.format_exc()) from e

    try:
        result = crew.kickoff(inputs=crew_inputs)
    except Exception as e:
        raise RuntimeError("crew.kickoff() crashed:\n" + traceback.format_exc()) from e


    def _read_json_artifact(rel_path: str, required_key: str) -> Optional[dict]:
        abs_path = os.path.join(CURRENT_DIR, rel_path)
        if not os.path.exists(abs_path):
            return None

        with open(abs_path, "r", encoding="utf-8") as f:
            txt = f.read().strip()

        # 1) Intento directo: el archivo es JSON puro
        try:
            obj = json.loads(txt)
            if isinstance(obj, dict) and required_key in obj:
                return obj
        except Exception:
            pass

        # 2) Fallback: buscar el primer objeto JSON embebido
        return _extract_json_object_with_key(txt, required_key)


    # después del kickoff:
    scene_blueprint_json = _read_json_artifact("artifacts/scene_blueprint.json", "scene_id")
    characters_json      = _read_json_artifact("artifacts/characters.json", "suspects")
    vision_json          = _read_json_artifact("artifacts/suspect_images.json", "suspect_images")
    solution_json = _read_json_artifact("artifacts/solution.json", "truth_summary")
    if solution_json:
        st.session_state.solution = solution_json


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
        summary = scene_blueprint_json.get("summary") or ""
        hidden_tension = scene_blueprint_json.get("hidden_tension") or ""
        full_ctx = summary.strip()
        if hidden_tension.strip():
            base_case["hidden_tension"] = hidden_tension.strip()    
        if full_ctx:
            base_case["context"] = full_ctx


        # Victim name from present_characters
        vname = scene_blueprint_json.get("victim_name")
        if isinstance(vname, str) and vname.strip():
            base_case["victim"] = vname.strip()

        # Victim role
        vrole = scene_blueprint_json.get("victim_role")
        if isinstance(vrole, str) and vrole.strip():
            base_case["victim_role"] = vrole.strip()


        t = scene_blueprint_json.get("time")
        ht = scene_blueprint_json.get("hidden_tension")
        if isinstance(ht, str) and ht.strip():
            base_case["hidden_tension"] = ht.strip()
        if isinstance(t, str) and t.strip():
            base_case["time"] = t.strip()
        elif summary:
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
                obj = _extract_json_object_with_key(raw, "suspects")
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
    if isinstance(vision_json, dict):
        vision_images = vision_json.get("suspect_images") or {}

    # Fallback: si no hay artifacts, intentar sacar suspect_images del result final
    if not vision_images:
        obj = _extract_json_object_with_key(str(result), "suspect_images")
        if obj and isinstance(obj.get("suspect_images"), dict):
            vision_images = obj.get("suspect_images") or {}

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
            "age": s.get("age"),
            "personality": s.get("personality", ""),
            "alibi": s.get("alibi", ""),
            "secret": s.get("secret_motivation", ""),
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
) -> dict:
    """
    Usa la Crew para generar la respuesta del sospechoso.
    """
    user_prompt = build_user_prompt(suspect_name, history, question)

    scene_blueprint = st.session_state.get("scene_blueprint")
    characters = st.session_state.get("characters")

    safe_scene_blueprint = sanitize_scene_blueprint_for_dialogue(scene_blueprint, suspect_name)
    safe_characters = sanitize_characters_for_dialogue(
        characters,
        suspect_name,
        redact_other_secrets=True,   # <- set False if you WANT suspects to know others' secrets (usually no)
    )

    crew_inputs = {
        "topic": CREW_TOPIC,
        "current_year": str(datetime.now().year),
        "game_state": json.dumps(
            {
                "victim": case.get("victim"),
                "time": case.get("time"),
                "place": case.get("place"),
                "cause": case.get("cause"),
                # optional: shorten this to avoid duplication; scene_blueprint.summary already has it
                "context": "",  
                "active_suspect": suspect_name,
            },
            ensure_ascii=False
        ),
        "player_action": user_prompt,
        "scene_blueprint": json.dumps(safe_scene_blueprint, ensure_ascii=False) if safe_scene_blueprint else "",
        "characters": json.dumps(safe_characters, ensure_ascii=False) if safe_characters else "",
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
            return {
                "spoken_text": (data.get("spoken_text") or data.get("answer") or data.get("text") or "").strip(),
                "inner_thoughts": (data.get("inner_thoughts") or "").strip(),
                "revealed_facts": data.get("revealed_facts") or [],
                "implied_clues": data.get("implied_clues") or [],
            }

        raw_fallback = str(result)
        data_fb = _extract_json_object_with_key(raw_fallback, "spoken_text")
        if isinstance(data_fb, dict):
            spoken_fb = data_fb.get("spoken_text") or data_fb.get("answer") or data_fb.get("text")
            if spoken_fb:
                return {"spoken_text": spoken_fb, "inner_thoughts": "", "revealed_facts": [], "implied_clues": []}

        answer_text = raw_fallback.strip()
        if len(answer_text) > 400:
            answer_text = answer_text[:400] + "..."
        return {"spoken_text": answer_text, "inner_thoughts": "", "revealed_facts": [], "implied_clues": []}

    except Exception as e:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "Quota exceeded" in msg:
            return {
                "spoken_text": (
                    "The overhead lights flicker and the network icon turns red. "
                    "«Systems are throttled… you won’t get more out of me right now,» "
                    "the suspect says, dodging your question."
                ),
                "inner_thoughts": "The system is throttled; I should stall and stay vague.",
                "revealed_facts": [],
                "implied_clues": ["System throttling occurred during interrogation (possible API quota)."],
            }

        return {
            "spoken_text": (
                "The suspect just stares back at you. "
                "Something in the system glitched and they refuse to answer."
            ),
            "inner_thoughts": f"Unexpected error: {msg[:120]}",
            "revealed_facts": [],
            "implied_clues": [],
        }



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
        st.session_state.suspect_memory = {s["name"]: {"revealed_facts": [], "implied_clues": []} for s in case["suspects"]}
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
    mem = st.session_state.get("suspect_memory", {}).get(suspect_name, {})
    facts = mem.get("revealed_facts", [])[:8]
    clues = mem.get("implied_clues", [])[:8]
    facts_txt = "\n".join([f"- {x}" for x in facts]) if facts else "- (none yet)"
    clues_txt = "\n".join([f"- {x}" for x in clues]) if clues else "- (none yet)"
        
    return f"""
INTERROGATION TARGET: {suspect_name}

INVESTIGATION MEMORY (what you have already stated / implied):
REVEALED FACTS:
{facts_txt}
IMPLIED CLUES:
{clues_txt}

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
        out = call_crew_for_answer(case, suspect_name, history, q)
        answer = out.get("spoken_text", "")


    answer = unescape(answer or "")
    answer = _strip_html_tags(answer)

    rf = out.get("revealed_facts") or []
    ic = out.get("implied_clues") or []
    history.append({"q": q, "a": answer, "revealed_facts": rf, "implied_clues": ic})

    mem = st.session_state.suspect_memory.get(suspect_name)
    if mem is not None:
        for item in rf:
            if item and item not in mem["revealed_facts"]:
                mem["revealed_facts"].append(item)
        for item in ic:
            if item and item not in mem["implied_clues"]:
                mem["implied_clues"].append(item)

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


    solution = st.session_state.get("solution") or {}
    truth = solution.get("truth_summary", "")
    method = solution.get("method", "")
    cover = solution.get("cover_up", "")
    motive = solution.get("motive", "")
    evidence = solution.get("key_evidence") or []
    timeline = solution.get("timeline") or []

    truth_block = ""
    if truth:
        truth_block += f"\n\n### What really happened\n{truth}\n"
    if method:
        truth_block += f"\n\n**Method:** {method}"
    if cover:
        truth_block += f"\n\n**Cover-up:** {cover}"
    if motive:
        truth_block += f"\n\n**Motive:** {motive}"
    if evidence:
        truth_block += "\n\n**Key evidence:**\n" + "\n".join([f"- {e}" for e in evidence[:5]])
    if timeline:
        truth_block += "\n\n**Timeline:**\n" + "\n".join([f"- {t}" for t in timeline[:5]])


    epilogue = _generate_epilogue(case, accused_name, won, guilty_name) + truth_block


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
            victim_role = escape(case.get("victim_role", "Unknown role"))
            time_ = escape(case.get("time", "Unknown time"))
            place = escape(case.get("place", "Unknown place"))
            cause = escape(case.get("cause", "Unknown cause"))
            ctx = case.get("context", "") or ""

            st.markdown(
                f"""
- **Victim:** {victim} — _{victim_role}_
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
                    if s.get("alibi"):
                        st.caption(f"**Alibi:** {s['alibi']}")

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
                    <span style="opacity:0.8;">Age: {escape(str(s.get('age','?')))} · Alibi: {escape(s.get('alibi',''))}</span><br/>
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
