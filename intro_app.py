import streamlit as st

def render_main_game():
    st.title("Main Game Placeholder")
    st.write("This is where the full game will appear.")

@st.dialog("How to Play")
def show_rules_dialog():
    st.markdown("""
    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; color: #31333F;">
        <ul>
            <li>There are <strong>4 suspects</strong>.</li>
            <li>You can interrogate them using <strong>free-form questions</strong>.</li>
            <li>Each suspect responds using an <strong>AI model</strong>.</li>
            <li>You have a <strong>limited number</strong> of total questions.</li>
            <li>When you are ready, you can <strong>accuse one suspect</strong>.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

@st.dialog("Tips")
def show_tips_dialog():
    st.markdown("""
    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; color: #31333F;">
        <ul>
            <li>Look for inconsistencies in their alibis.</li>
            <li>Pay attention to the tone of their responses.</li>
            <li>Use your questions wisely.</li>
            <li>Check the timeline carefully.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

def render_intro():
    # CSS for specific styling requirements
    st.markdown("""
        <style>
            /* Hide Streamlit Header, Footer, and Toolbar */
            header {visibility: hidden;}
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            [data-testid="stToolbar"] {visibility: hidden; display: none;}
            
            /* Remove vertical scroll / tight layout */
            .block-container {
                padding-top: 2rem;
                padding-bottom: 0rem;
                max-width: 800px;
            }

            /* Center Title and Subtitle + Increase Size */
            h1 {
                text-align: center;
                margin-bottom: 0px;
                font-size: 3.5rem !important; /* Bigger Title */
            }
            .subtitle {
                text-align: center;
                color: grey;
                font-size: 2.5rem; /* Bigger Subtitle */
                margin-top: -10px;
                margin-bottom: 30px;
            }

            /* ICON BUTTON STYLING (Secondary Buttons) */
            /* Target specific container inside button to force font size */
            button[kind="secondary"] {
                background-color: transparent !important;
                border: none !important;
                box-shadow: none !important;
                height: auto !important;
                padding: 10px !important;
            }
            
            /* This targets the emoji text directly */
            button[kind="secondary"] p {
                font-size: 4rem !important; /* ~2.5x standard size */
                line-height: 1 !important;
                margin-bottom: 0px !important;
            }

            button[kind="secondary"]:hover {
                color: #ff4b4b !important;
                background-color: transparent !important;
                transform: scale(1.1);
                transition: transform 0.2s;
            }
            button[kind="secondary"]:focus {
                box-shadow: none !important;
                outline: none !important;
            }

            /* START GAME BUTTON STYLING (Primary Button) */
            button[kind="primary"] {
                background-color: #FF0000 !important; /* Bright Red */
                color: white !important;
                font-size: 1.5rem !important;
                font-weight: bold !important;
                padding: 0.75rem 2rem !important;
                border-radius: 8px !important;
                border: none !important;
                margin: 20px auto !important;
                display: block !important;
                width: 50% !important;
            }
            button[kind="primary"]:hover {
                background-color: #CC0000 !important;
            }

            /* Dialog Box Styling */
            div[data-testid="stDialog"] div[role="dialog"] {
                background-color: #FFF9E6; 
            }
        </style>
    """, unsafe_allow_html=True)

    # 1. Title Area
    st.title("AI Murder Mystery")
    st.markdown('<p class="subtitle">Solve the case. Find the killer.</p>', unsafe_allow_html=True)

    # 2. Icons Area (Centered)
    # Using columns to center the icons nicely
    col_spacer_l, col_book, col_spacer_m, col_bulb, col_spacer_r = st.columns([2, 1, 0.5, 1, 2])
    
    with col_book:
        if st.button("📖", key="btn_rules", help="How to Play"):
            show_rules_dialog()
            
    with col_bulb:
        if st.button("💡", key="btn_tips", help="Tips"):
            show_tips_dialog()

    # 3. Start Game Button (Centered)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("Start Game", type="primary"):
            st.session_state["game_started"] = True
            st.rerun()

def main():
    st.set_page_config(page_title="AI Murder Mistery", layout="centered")

    # Initialize session state
    if "game_started" not in st.session_state:
        st.session_state["game_started"] = False

    # Routing
    if st.session_state["game_started"]:
        render_main_game()
    else:
        render_intro()

if __name__ == "__main__":
    main()