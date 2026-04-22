import gradio as gr

def status():
    return "Asset Tracker Bot is running!"

gr.Interface(fn=status, inputs=[], outputs="text", title="Asset Tracker").launch()
