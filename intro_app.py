import streamlit as st
import streamlit.components.v1 as components
from app import render_game


# --- Page Configuration & CSS ---
def configure_page():
    st.set_page_config(
        page_title="AI Murder Mystery",
        layout="centered",
        initial_sidebar_state="collapsed"
    )

    # Global CSS
    st.markdown("""
        <style>
            /* 1. Hide Streamlit Chrome */
            #MainMenu, footer, header {visibility: hidden;}
            .stDeployButton {display: none;}
            
            /* 2. Main Layout */
            .stApp {
                background-color: white;
            }
            .block-container {
                padding-top: 2rem;
                padding-bottom: 0rem;
            }

            /* 3. MODAL Styles */
            .modal-backdrop {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background-color: rgba(0, 0, 0, 0.6);
                backdrop-filter: blur(4px);
                z-index: 9998;
                display: flex;
                justify-content: center;
                align-items: flex-start;
            }
            
            .modal-card {
                background-color: #f0f7ff;
                border: 2px solid #3b82f6;
                border-radius: 15px;
                padding: 40px;
                width: 600px;
                max-width: 90%;
                margin-top: 15vh;
                box-shadow: 0 10px 25px rgba(0,0,0,0.3);
                position: relative;
                color: #1e3a8a;
            }
            
            .modal-title {
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 20px;
                border-bottom: 2px solid #bfdbfe;
                padding-bottom: 10px;
            }
            
            .modal-body {
                font-size: 18px;
                line-height: 1.6;
                color: #333;
            }
            
            /* 4. MODAL CLOSE BUTTON (HTML) */
            .modal-close {
                position: absolute;
                top: 15px;
                right: 20px;
                font-size: 28px;
                cursor: pointer;
                color: #ef4444;
                font-weight: bold;
                line-height: 1;
                user-select: none;
                transition: transform 0.2s;
            }
            .modal-close:hover {
                color: #b91c1c;
                transform: scale(1.2);
            }

            /* 5. TOP ICONS STYLE (HTML) */
            .icon-bar {
                display: flex;
                justify-content: center;
                gap: 50px;
                margin-bottom: 50px; /* Aumentado para equilibrar espacio inferior */
                margin-top: 50px;    /* Aumentado para bajarlos y centrarlos */
            }
            
            .top-icon {
                font-size: 55px;
                cursor: pointer;
                user-select: none;
                transition: transform 0.2s;
                line-height: 1;
            }
            
            .top-icon:hover {
                transform: scale(1.15);
            }

            /* 6. START GAME BUTTON STYLE */
            button[kind="primary"] {
                background-color: #dc2626 !important;
                color: white !important;
                border-radius: 12px !important;
                font-size: 32px !important;
                padding: 20px 50px !important;
                border: none !important;
                box-shadow: 0 4px 6px rgba(0,0,0,0.2) !important;
                margin-top: 20px !important;
                width: 100% !important;
            }
            button[kind="primary"]:hover {
                background-color: #b91c1c !important;
                box-shadow: 0 6px 8px rgba(0,0,0,0.3) !important;
            }
            
            hr { display: none !important; }

        </style>
    """, unsafe_allow_html=True)

# --- State Management ---
def init_state():
    if "game_started" not in st.session_state:
        st.session_state["game_started"] = False
    if "modal_open" not in st.session_state:
        st.session_state["modal_open"] = None

# --- Callbacks ---
def toggle_rules_modal():
    st.session_state["modal_open"] = "rules"

def toggle_tips_modal():
    st.session_state["modal_open"] = "tips"

def close_callback():
    st.session_state["modal_open"] = None

def start_game_action():
    st.session_state["game_started"] = True

# --- Modal Rendering ---
def render_modal_content():
    if st.session_state["modal_open"] == "rules":
        title = "How to Play"
        content = """
        <ul>
            <li>There are <b>4 suspects</b> in the case.</li>
            <li>You can interrogate them using <b>free-form questions</b>.</li>
            <li>Each suspect responds with their own <b>AI personality</b>.</li>
            <li>You have a <b>limited number</b> of questions.</li>
            <li>In the end, you must <b>accuse</b> one to win.</li>
        </ul>
        """
    elif st.session_state["modal_open"] == "tips":
        title = "Detective Tips"
        content = """
        <ul>
            <li><b>Cross-reference:</b> Ask the same thing to multiple suspects.</li>
            <li><b>Be specific:</b> Ask for exact details (time, location).</li>
            <li>Look for <b>contradictions</b> in their alibis.</li>
            <li>Manage your questions well, they are limited!</li>
            <li>Take notes on the timelines.</li>
        </ul>
        """
    else:
        return

    # Render Modal HTML (Backdrop + Card + HTML Close Button)
    st.markdown(f"""
        <div class="modal-backdrop">
            <div class="modal-card">
                <div id="modal_close" class="modal-close">✖</div>
                <div class="modal-title">{title}</div>
                <div class="modal-body">{content}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

# --- Intro Page Rendering ---
def render_intro():
    # Title
    st.markdown("<h1 style='text-align: center; color: black; font-size: 3.5rem;'>AI Murder Mystery</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: #666;'>Solve the case. Find the killer.</h3>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # --- 1. HTML ICONS (No inline onclick, we use IDs) ---
    st.markdown("""
        <div class="icon-bar">
            <span id="rules_icon" class="top-icon">📖</span>
            <span id="tips_icon"  class="top-icon">💡</span>
        </div>
    """, unsafe_allow_html=True)

    # --- 2. HIDDEN STREAMLIT BUTTONS ---
    # We render them normally, but rely on JS to hide them and click them.
    # The text MUST match exactly what the JS looks for.
    st.button("rules_hidden", key="rules_hidden", on_click=toggle_rules_modal)
    st.button("tips_hidden", key="tips_hidden", on_click=toggle_tips_modal)
    st.button("close_hidden", key="close_hidden", on_click=close_callback)

    # --- 3. JAVASCRIPT GLUE (Using components.html) ---
    # This runs in an iframe, accesses the parent document, and orchestrates the clicks.
    components.html("""
    <script>
        const doc = window.parent.document;
        
        // Helper to find specific Streamlit buttons by text
        function getStreamlitButton(text) {
            const buttons = Array.from(doc.querySelectorAll('button'));
            return buttons.find(btn => btn.innerText === text);
        }

        // We use an interval to handle Streamlit's dynamic re-rendering
        setInterval(() => {
            // 1. Find and Hide the Helper Buttons
            const btnRules = getStreamlitButton("rules_hidden");
            const btnTips = getStreamlitButton("tips_hidden");
            const btnClose = getStreamlitButton("close_hidden");

            if (btnRules) btnRules.style.display = "none";
            if (btnTips) btnTips.style.display = "none";
            if (btnClose) btnClose.style.display = "none";

            // 2. Link Rules Icon
            const iconRules = doc.getElementById("rules_icon");
            if (iconRules && btnRules) {
                iconRules.onclick = function() { btnRules.click(); };
            }

            // 3. Link Tips Icon
            const iconTips = doc.getElementById("tips_icon");
            if (iconTips && btnTips) {
                iconTips.onclick = function() { btnTips.click(); };
            }

            // 4. Link Close Icon (inside Modal)
            const iconClose = doc.getElementById("modal_close");
            if (iconClose && btnClose) {
                iconClose.onclick = function() { btnClose.click(); };
            }

        }, 300); // Check every 300ms
    </script>
    """, height=0)

    # --- 4. MODAL RENDERING ---
    if st.session_state["modal_open"]:
        render_modal_content()

    # Start Game Button (Centered)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.button("START GAME", key="start_game", on_click=start_game_action, type="primary")

def render_main_game():
    # Aquí pintamos el juego real
    render_game()

    # Botón para volver a la intro
    if st.button("Back to Intro"):
        st.session_state["game_started"] = False
        st.rerun()

# --- Main ---
def main():
    configure_page()
    init_state()

    if st.session_state["game_started"]:
        render_main_game()
    else:
        render_intro()

if __name__ == "__main__":
    main()