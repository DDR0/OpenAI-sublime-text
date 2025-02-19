from enum import Enum
from typing import List, Optional
from threading import Event
import sublime
from sublime_plugin import TextCommand, EventListener
from sublime import Settings, View, Region, Edit
import functools
from .cacher import Cacher
from .errors.OpenAIException import WrongUserInputException, present_error
from .assistant_settings import CommandMode
from .openai_worker import OpenAIWorker

class Openai(TextCommand):
    stop_event: Event = Event()
    worker_thread: Optional[OpenAIWorker] = None

    def on_input(self, region: Optional[Region], text: str, view: View, mode: str, input: str):
        from .openai_worker import OpenAIWorker # https://stackoverflow.com/a/52927102

        Openai.stop_worker()  # Stop any existing worker before starting a new one
        Openai.stop_event.clear()

        Openai.worker_thread = OpenAIWorker(stop_event=self.stop_event, region=region, text=text, view=view, mode=mode, command=input)
        Openai.worker_thread.start()

    """
    asyncroniously send request to https://api.openai.com/v1/completions
    with the selcted text of the view
    and inserts suggestion from within response at place of `[insert]` placeholder
    """
    def run(self, edit: Edit, **kwargs):
        from .output_panel import SharedOutputPanelListener # https://stackoverflow.com/a/52927102

        global settings
        plugin_loaded()
        mode = kwargs.get('mode', 'chat_completion')

        # get selected text
        region: Optional[Region] = None
        text: Optional[str] = ""
        for region in self.view.sel():
            if not region.empty():
                text += self.view.substr(region)

        # Checking that user select some text
        try:
            if region and len(region) < settings.get("minimum_selection_length"):
                if mode == CommandMode.chat_completion:
                    raise WrongUserInputException("Not enough text selected to complete the request, please expand the selection.")
        except WrongUserInputException as error:
            present_error(title="OpenAI error", error=error)
            return

        if mode == CommandMode.reset_chat_history.value:
            Cacher().drop_all()
            # FIXME: This is broken, beacuse it specified on panel
            output_panel = sublime.active_window().find_output_panel("OpenAI Chat")
            output_panel.set_read_only(False)
            region = Region(0, output_panel.size())
            output_panel.erase(edit, region)
            output_panel.set_read_only(True)

        elif mode == CommandMode.create_new_tab.value:
            window = sublime.active_window()
            listner = SharedOutputPanelListener(markdown=settings.get('markdown'))
            listner.create_new_tab(window)
            # listner.toggle_overscroll(window=window, enabled=True)
            listner.refresh_output_panel(window=window)

        elif mode == CommandMode.refresh_output_panel.value:
            window = sublime.active_window()
            listner = SharedOutputPanelListener(markdown=settings.get('markdown'))
            # listner.toggle_overscroll(window=window, enabled=False)
            listner.refresh_output_panel(window=window)
            listner.show_panel(window=window)

        elif mode == CommandMode.chat_completion.value:
            sublime.active_window().show_input_panel(
                "Question: ",
                "",
                functools.partial(
                    self.on_input,
                    region if region else None,
                    text,
                    self.view,
                    mode
                ),
                None,
                None
            )

    # TODO: To chech if this is even necessary
    @classmethod
    def stop_worker(cls):
        if cls.worker_thread and cls.worker_thread.is_alive():
            cls.stop_event.set()  # Signal the thread to stop
            cls.worker_thread = None

class ActiveViewEventListener(EventListener):
    def on_activated(self, view: View):
        global settings
        plugin_loaded()
        assistant = Cacher().read_model()
        status_hint_options: Optional[List[str]] = settings.get('status_hint', [])

        if assistant and 'name' in assistant and 'prompt_mode' in assistant and 'chat_model' in assistant:
            if status_hint_options:
                if len(status_hint_options) > 1:
                    if StatusBarMode._name.value in status_hint_options and StatusBarMode.prompt_mode.value in status_hint_options and StatusBarMode.chat_model.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'[{assistant["name"].title()} | {assistant["prompt_mode"].title()} | {assistant["chat_model"].upper()}]')
                    elif StatusBarMode._name.value in status_hint_options and StatusBarMode.prompt_mode.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'[{assistant["name"].title()} | {assistant["prompt_mode"].title()}]')
                    elif StatusBarMode._name.value in status_hint_options and StatusBarMode.chat_model.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'[{assistant["name"].title()} | {assistant["chat_model"].upper()}]')
                    elif StatusBarMode.prompt_mode.value in status_hint_options and StatusBarMode.chat_model.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'[{assistant["prompt_mode"].title()} | {assistant["chat_model"].upper()}]')
                elif len(status_hint_options) == 1:
                    if StatusBarMode._name.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'{assistant["name"].title}')
                    if StatusBarMode.prompt_mode.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'{assistant["prompt_mode"].title}')
                    if StatusBarMode.chat_model.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'{assistant["chat_model"].upper}')
                else: # status_hint_options is None or len(status_hint_options) == 0
                    pass

settings: Optional[Settings] = None

def plugin_loaded():
    global settings
    settings = sublime.load_settings("openAI.sublime-settings")

class StatusBarMode(Enum):
    _name = "name"
    prompt_mode = "prompt_mode"
    chat_model = "chat_model"
