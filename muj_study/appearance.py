"""Persist appearance and keep Streamlit's native widgets in the same mode."""
import re

from .core import App


PALETTES = {
    'dark': {'base': 'dark', 'primaryColor': '#FF2D95', 'backgroundColor': '#0A0A0A', 'secondaryBackgroundColor': '#131B24', 'textColor': '#F1F5FA'},
    'light': {'base': 'light', 'primaryColor': '#007BA7', 'backgroundColor': '#F5F8FC', 'secondaryBackgroundColor': '#EAF1F7', 'textColor': '#14232E'},
}


def set_mode(app, mode):
    if mode not in PALETTES: raise ValueError('Unknown appearance mode')
    app.cfg['appearance'] = mode
    app.save_config()
    path = app.config_path.parent / '.streamlit' / 'config.toml'
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding='utf-8') if path.exists() else '[theme]\n'
    section = '[theme]\n' + ''.join(f'{key} = "{value}"\n' for key, value in PALETTES[mode].items()) + 'font = "sans serif"\n\n'
    if re.search(r'^\[theme\]\s*$', text, re.M):
        text = re.sub(r'^\[theme\]\s*\n.*?(?=^\[|\Z)', lambda _: section, text, count=1, flags=re.M | re.S)
    else: text = section + text
    path.write_text(text, encoding='utf-8')


def toggle(config, data):
    import streamlit as st
    from streamlit import config as streamlit_config
    app = App(config, data)
    try: set_mode(app, 'light' if app.cfg.get('appearance', 'dark') == 'dark' else 'dark')
    finally: app.close()
    # Reload native theme colors, including canvas-rendered dataframes. A second
    # full run sends the updated theme to the browser without restarting workers.
    streamlit_config.get_config_options(force_reparse=True)
    st.session_state['_theme_changed'] = True
