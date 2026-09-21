"""启动 Gradio 界面。"""
import sys, gradio as gr
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.gradio_app import create_app

print("启动中...")
app = create_app()
print("Gradio 界面启动中...")
app.launch(server_name="127.0.0.1", server_port=7860, share=False,
           inbrowser=False, quiet=True, theme=gr.themes.Soft())
print("已启动")
