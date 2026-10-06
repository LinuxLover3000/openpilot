"""NAP settings panel for the comma 4 / mici UI tree.

Mirrors selfdrive/ui/layouts/settings/nap.py for the BigButton/NavScroller
vocabulary used on the comma 4. Phase 1 stub: three controls (pedal
interceptor toggle, radar enabled toggle, flash EPAS button).
Subsequent phases add the rest.
"""
from openpilot.common.params import Params
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets.scroller import NavScroller
from openpilot.selfdrive.ui.mici.widgets.button import BigButton
from openpilot.selfdrive.ui.mici.widgets.dialog import BigConfirmationDialog
from openpilot.selfdrive.ui.mici.layouts.settings.nap_script import launch_script
from openpilot.selfdrive.ui.layouts.settings.nap_content import (
  BACKUP_EPAS_INSTRUCTIONS,
  FLASH_EPAS_INSTRUCTIONS,
  RESTORE_EPAS_INSTRUCTIONS,
)
from openpilot.selfdrive.ui.ui_state import ui_state
from opendbc.car.tesla.preap.nap_params import NAPParamKeys


def _reboot_dialog() -> None:
  def confirm():
    Params().put_bool("DoReboot", True)
  icon = gui_app.texture("icons_mici/settings/device/reboot.png", 64, 70)
  gui_app.push_widget(BigConfirmationDialog("slide to\nreboot now", icon, confirm))


def _reboot_on_toggle(_):
  _reboot_dialog()


def _confirm_then_flash(slider_title: str, runner_title: str, instructions: str, module: str):
  """Slide-to-confirm dialog before launching a destructive EPAS script.

  Adds a deliberate gesture before an irreversible firmware operation.
  Read-only operations (extract, calibration, test) skip this.
  """
  def confirm():
    launch_script(runner_title, instructions, module)
  icon = gui_app.texture("icons_mici/buttons/button_circle_red.png", 180, 180)
  gui_app.push_widget(BigConfirmationDialog(slider_title, icon, confirm, red=True))


class NAPLayoutMici(NavScroller):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._params.put_bool(NAPParamKeys.FORCE_PRE_AP, True)

    # set_enabled accepts bool | Callable[[], bool]. Pass methods directly
    # (e.g. ui_state.is_offroad), NOT lambdas-wrapping-methods. The form
    # `lambda: ui_state.is_offroad` returns the bound method object —
    # always truthy — and silently leaves destructive actions clickable
    # while onroad.

    # ── Actions ──────────────────────────────────────
    backup_epas_btn = BigButton("backup epas", "extract")
    backup_epas_btn.set_click_callback(
      lambda: launch_script("Backup EPAS Firmware", BACKUP_EPAS_INSTRUCTIONS,
                            "scripts.nap.extract_epas",
                            ))
    backup_epas_btn.set_enabled(ui_state.is_offroad)

    flash_epas_btn = BigButton("flash epas", "flash")
    flash_epas_btn.set_click_callback(
      lambda: _confirm_then_flash(
        "slide to\nflash epas",
        "Flash EPAS Firmware", FLASH_EPAS_INSTRUCTIONS, "scripts.nap.flash_epas",
      ))
    flash_epas_btn.set_enabled(ui_state.is_offroad)

    restore_epas_btn = BigButton("restore epas", "restore")
    restore_epas_btn.set_click_callback(
      lambda: _confirm_then_flash(
        "slide to\nrestore epas",
        "Restore EPAS Firmware", RESTORE_EPAS_INSTRUCTIONS, "scripts.nap.restore_epas",
      ))
    restore_epas_btn.set_enabled(ui_state.is_offroad)

    self._scroller.add_widgets([
      backup_epas_btn,
      flash_epas_btn,
      restore_epas_btn,
    ])
