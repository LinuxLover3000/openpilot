import os
import subprocess
import pyray as rl
from openpilot.common.params import Params
from openpilot.common.basedir import BASEDIR
from openpilot.system.ui.widgets import Widget, DialogResult
from openpilot.system.ui.widgets.keyboard import Keyboard
from openpilot.system.ui.widgets.list_view import (
  toggle_item, multiple_button_item, button_item, text_item,
  ITEM_PADDING,
)
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets.html_render import HtmlRenderer, ElementType
from openpilot.selfdrive.ui.layouts.settings.nap_content import (
  BACKUP_EPAS_INSTRUCTIONS, BRAKE_FACTOR_PRESETS,
  CALIBRATE_PEDAL_INSTRUCTIONS, CALIBRATE_RADAR_INSTRUCTIONS,
  FLASH_EPAS_INSTRUCTIONS, PEDAL_CAN_BUS_VALUES,
  RADAR_OFFSET_MAX, RADAR_OFFSET_MIN,
  RESTORE_EPAS_INSTRUCTIONS, TEST_RADAR_INSTRUCTIONS,
  acknowledgments_html, find_preset_index,
)
from opendbc.car.tesla.preap.nap_params import NAPParamKeys, DEFAULTS
from openpilot.selfdrive.ui.ui_state import ui_state


class SectionHeader(Widget):
  """Lightweight section label to visually separate groups of settings."""

  HEADER_HEIGHT = 70

  def __init__(self, title: str):
    super().__init__()
    self._title = title
    self._font = gui_app.font(FontWeight.BOLD)
    self.set_rect(rl.Rectangle(0, 0, 0, self.HEADER_HEIGHT))

  def set_parent_rect(self, parent_rect: rl.Rectangle):
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  def _render(self, rect):
    text_size = measure_text_cached(self._font, self._title, 40)
    text_y = self._rect.y + (self._rect.height - text_size.y) / 2
    rl.draw_text_ex(
      self._font, self._title,
      rl.Vector2(self._rect.x + ITEM_PADDING, text_y),
      40, 0, rl.Color(180, 180, 180, 255),
    )


class CreditsBlock(Widget):
  """Static block of HTML-rendered credits text with auto-sized height."""

  def __init__(self, html: str):
    super().__init__()
    self._html = HtmlRenderer(
      text=html,
      text_size={ElementType.P: 40},
      text_color=rl.Color(140, 140, 140, 255),
    )
    self.set_rect(rl.Rectangle(0, 0, 0, 200))  # placeholder height

  def set_parent_rect(self, parent_rect: rl.Rectangle):
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width
    content_w = int(self._rect.width - ITEM_PADDING * 2)
    self._rect.height = self._html.get_total_height(content_w) + ITEM_PADDING

  def _render(self, rect):
    content_w = int(self._rect.width - ITEM_PADDING * 2)
    h = self._html.get_total_height(content_w)
    html_rect = rl.Rectangle(
      self._rect.x + ITEM_PADDING, self._rect.y,
      content_w, h,
    )
    self._html.set_rect(html_rect)
    self._html.render(html_rect)


def section_header_item(title: str) -> SectionHeader:
  return SectionHeader(title)


class NAPLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._build_items()
    self._scroller = Scroller(self._all_items, line_separator=True, spacing=0)

  def _build_items(self):
    """Build all list items organized into sections."""
    self._all_items = []
    self._toggle_map = {}  # param_key -> ListItem (for refresh)

    # ── Section 6: Actions ──
    self._all_items.append(section_header_item("Actions"))

    self._backup_epas_btn = button_item(
      "Backup EPAS",
      "Extract",
      description="Extract and save stock EPAS firmware image without flashing.",
      callback=self._on_backup_epas,
    )
    self._backup_epas_btn.action_item.set_enabled(ui_state.is_offroad)
    self._all_items.append(self._backup_epas_btn)

    self._flash_epas_btn = button_item(
      "Flash EPAS",
      "Flash",
      description="Flash the EPAS (Electric Power Assisted Steering) firmware.",
      callback=self._on_flash_epas,
    )
    self._flash_epas_btn.action_item.set_enabled(ui_state.is_offroad)
    self._all_items.append(self._flash_epas_btn)

    self._restore_epas_btn = button_item(
      "Restore EPAS",
      "Restore",
      description="Restore stock EPAS firmware image.",
      callback=self._on_restore_epas,
    )
    self._restore_epas_btn.action_item.set_enabled(ui_state.is_offroad)
    self._all_items.append(self._restore_epas_btn)

    self._emergency_disable_btn = button_item(
      "Emergency Disable",
      "Disable",
      description="Immediately disable pedal interceptor and clear calibration. Restart required.",
      callback=self._on_emergency_disable,
    )
    self._all_items.append(self._emergency_disable_btn)

    self._reset_defaults_btn = button_item(
      "Reset to Defaults",
      "Reset",
      description="Reset all steering settings to factory defaults. This cannot be undone.",
      callback=self._on_reset_defaults,
    )
    self._reset_defaults_btn.action_item.set_enabled(ui_state.is_offroad)
    self._all_items.append(self._reset_defaults_btn)

    # ── Acknowledgments ──
    self._all_items.append(section_header_item("Acknowledgments"))
    self._all_items.append(CreditsBlock(acknowledgments_html()))

  def _add_toggle(self, param_key: str, title: str, description: str,
                   enabled: bool | None = None, needs_reboot: bool = False):
    """Helper to add a toggle item and register it for state refresh."""
    kwargs = {}
    if enabled is not None:
      kwargs['enabled'] = enabled

    def on_toggle(state, k=param_key):
      self._params.put_bool(k, state)
      if needs_reboot:
        self._show_reboot_modal()

    item = toggle_item(
      title,
      description=description,
      initial_state=self._params.get_bool(param_key),
      callback=on_toggle,
      **kwargs,
    )
    self._toggle_map[param_key] = item
    self._all_items.append(item)

  # ── Script runner ──

  def _show_script_runner(self, title: str, instructions: str, script_module: str):
    """Launch the script runner as a separate process that takes over the screen."""
    script_path = os.path.join(BASEDIR, "scripts", "nap", "run_script.py")
    log_path = "/tmp/nap_script_runner.log"

    with open(log_path, "w") as log_file:
      subprocess.Popen(
        ["python", script_path, title, script_module, instructions],
        cwd=BASEDIR,
        start_new_session=True,
        stdout=log_file,
        stderr=log_file,
      )

  # ── Action button callbacks ──

  def _on_calibrate_pedal(self):
    self._show_script_runner(
      title="Pedal Calibration",
      instructions=CALIBRATE_PEDAL_INSTRUCTIONS,
      script_module="scripts.nap.calibrate_pedal",
    )

  def _on_flash_epas(self):
    self._show_script_runner(
      title="Flash EPAS Firmware",
      instructions=FLASH_EPAS_INSTRUCTIONS,
      script_module="scripts.nap.flash_epas",
    )

  def _on_backup_epas(self):
    self._show_script_runner(
      title="Backup EPAS Firmware",
      instructions=BACKUP_EPAS_INSTRUCTIONS,
      script_module="scripts.nap.extract_epas",
    )

  def _on_restore_epas(self):
    self._show_script_runner(
      title="Restore EPAS Firmware",
      instructions=RESTORE_EPAS_INSTRUCTIONS,
      script_module="scripts.nap.restore_epas",
    )

  def _show_reboot_modal(self):
    """Show a modal prompting the user to reboot for the change to take effect."""
    def confirm_callback(result: int):
      if result == DialogResult.CONFIRM:
        self._params.put_bool("DoReboot", True)

    content = "<h1>Reboot Required</h1><br><p>This change requires a reboot to take effect.</p>"
    dlg = ConfirmDialog(content, "Reboot", cancel_text="Ignore", rich=True, callback=confirm_callback)
    gui_app.push_widget(dlg)

  def _on_emergency_disable(self):
    def confirm_callback(result: int):
      if result == DialogResult.CONFIRM:
        self._params.put_bool(NAPParamKeys.PEDAL_ENABLED, False)
        self._params.put_bool(NAPParamKeys.PEDAL_CALIB_DONE, False)
        self._refresh_toggles()

    content = (
      "<h1>Emergency Disable</h1><br>"
      + "<p>This will disable the pedal interceptor and clear calibration. "
      + "You will need to restart the device for changes to take effect.</p>"
    )
    dlg = ConfirmDialog(content, "Disable", rich=True, callback=confirm_callback)
    gui_app.push_widget(dlg)

  def _on_reset_defaults(self):
    def confirm_callback(result: int):
      if result == DialogResult.CONFIRM:
        self._reset_all_to_defaults()
        self._refresh_toggles()

    content = (
      "<h1>Reset to Defaults</h1><br>"
      + "<p>This will reset all steering settings to their factory default values. "
      + "This action cannot be undone.</p>"
    )
    dlg = ConfirmDialog(content, "Reset All", rich=True, callback=confirm_callback)
    gui_app.push_widget(dlg)

  def _reset_all_to_defaults(self):
    """Write default value for each NAP param."""
    for key, default in DEFAULTS.items():
      if isinstance(default, bool):
        self._params.put_bool(key, default)
      elif isinstance(default, (int, float)):
        self._params.put(key, default)
    # Force Pre-AP is locked on in the panel but DEFAULTS keeps it off
    # for non-UI consumers. Re-apply the lock after the wholesale loop
    # so reset doesn't silently flip the invariant.
    self._params.put_bool(NAPParamKeys.FORCE_PRE_AP, True)

  # ── Render / lifecycle ──

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()
    self._refresh_toggles()

  def _refresh_toggles(self):
    """Sync all toggle states from params (handles external changes)."""
    for key, item in self._toggle_map.items():
      item.action_item.set_state(self._params.get_bool(key))
