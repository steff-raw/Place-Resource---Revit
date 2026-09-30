# -*- coding: utf-8 -*-
"""Dialogs that work under the pyRevit CPython engine.

pyRevit replaces every ``pyrevit.forms`` member with a stub under CPython
(``PyRevitCPythonNotSupported``), including ``alert``, ``SelectFromList``,
``CommandSwitchWindow``, ``FlexForm`` and ``pick_file``. This module uses the
Revit ``TaskDialog`` and Windows Forms through pythonnet instead.

Flag enums are never combined with ``|``, so nothing depends on pythonnet
enum arithmetic.
"""

_COMMAND_LINKS = ("CommandLink1", "CommandLink2", "CommandLink3", "CommandLink4")


def alert(message, title="Place Resource"):
    """Show a message with an OK button."""
    from Autodesk.Revit.UI import TaskDialog
    trail_step("showing message: {0}".format(title))
    TaskDialog.Show(title, message)


def choose_command(title, instruction, options, content=None, footer=None):
    """Show up to four command links and return the key of the one clicked.

    ``options`` is a list of ``(key, label)`` or ``(key, label, detail)``.
    Returns None when the user cancels or closes the dialog.
    """
    from Autodesk.Revit.UI import (
        TaskDialog,
        TaskDialogCommandLinkId,
        TaskDialogCommonButtons,
        TaskDialogResult,
    )
    if not options or len(options) > len(_COMMAND_LINKS):
        raise ValueError("choose_command needs between 1 and 4 options.")
    dialog = TaskDialog(title)
    dialog.MainInstruction = instruction
    if content:
        dialog.MainContent = content
    if footer:
        dialog.FooterText = footer
    dialog.CommonButtons = TaskDialogCommonButtons.Cancel
    results = []
    for index, option in enumerate(options):
        link_name = _COMMAND_LINKS[index]
        key, label = option[0], option[1]
        detail = option[2] if len(option) > 2 else None
        link_id = getattr(TaskDialogCommandLinkId, link_name)
        if detail:
            dialog.AddCommandLink(link_id, label, detail)
        else:
            dialog.AddCommandLink(link_id, label)
        results.append((getattr(TaskDialogResult, link_name), key))
    trail_step("showing choice: {0}".format(instruction))
    result = dialog.Show()
    for link_result, key in results:
        if result == link_result:
            return key
    return None


def ask_yes_no(title, instruction, content=None, yes_label="Yes", no_label="No"):
    """Return True only when the user picks the first option."""
    choice = choose_command(title, instruction, [("yes", yes_label), ("no", no_label)], content=content)
    return choice == "yes"


BASE_WIDTH = 820
BASE_HEIGHT = 600
MIN_WIDTH = 520
MIN_HEIGHT = 360
COMPACT_WIDTH = 520
COMPACT_HEIGHT = 200
PROMPT_HEIGHT = 64
BUTTON_BAR_HEIGHT = 52
BUTTON_WIDTH = 110
BUTTON_HEIGHT = 34
FONT_NAME = "Segoe UI"
FONT_SIZE = 10.0


def scaled(value, factor):
    """Scale a size in logical pixels (96 dpi) to device pixels. Never below 1."""
    return max(1, int(float(value) * float(factor or 1.0) + 0.5))


def row_labels(labels, details=None):
    """Join each label with its detail text, if any: 'Label - detail'."""
    rows = []
    details = list(details or [])
    for index, label in enumerate(labels):
        text = str(label)
        detail = details[index] if index < len(details) else None
        if detail:
            text = "{0} - {1}".format(text, detail)
        rows.append(text)
    return rows


def choose_from_list(title, labels, prompt=None, button_text="Select", selected_index=0, details=None):
    """Pick one entry from a list. Returns its index, or None when cancelled.

    ``details`` is an optional list of one-line explanations shown after each label.
    No Python event handlers are attached to the form, so .NET never calls back
    into Python while the dialog is open. Select an item and press the button.
    """
    rows = row_labels(labels, details)
    if not rows:
        return None
    _load_winforms()
    from System.Windows.Forms import DialogResult, ListBox
    box = ListBox()
    for row in rows:
        box.Items.Add(row)
    box.SelectedIndex = selected_index if selected_index is not None and 0 <= selected_index < len(rows) else 0
    form = _build_form(title, prompt or "Select one item, then press {0}.".format(button_text), button_text, box)
    try:
        trail_step("showing list: {0}".format(title))
        result = form.ShowDialog()
        if result != DialogResult.OK or box.SelectedIndex < 0:
            return None
        return int(box.SelectedIndex)
    finally:
        form.Dispose()


def choose_many_from_list(title, labels, preselected=None, prompt=None, button_text="OK", details=None):
    """Tick several entries in a checklist. Returns the ticked indexes in list order, or None when cancelled.

    ``preselected`` is an iterable of indexes that start ticked. Like ``choose_from_list``,
    no Python event handlers are attached.
    """
    rows = row_labels(labels, details)
    if not rows:
        return None
    _load_winforms()
    from System.Windows.Forms import CheckedListBox, DialogResult
    box = CheckedListBox()
    box.CheckOnClick = True
    for row in rows:
        box.Items.Add(row)
    for index in checked_indexes(preselected, len(rows)):
        box.SetItemChecked(index, True)
    form = _build_form(title, prompt or "Tick the items to include, then press {0}.".format(button_text), button_text, box)
    try:
        trail_step("showing tick list: {0}".format(title))
        result = form.ShowDialog()
        if result != DialogResult.OK:
            return None
        return sorted(int(index) for index in box.CheckedIndices)
    finally:
        form.Dispose()


def _build_form(title, prompt, button_text, box, compact=False):
    """A resizable window: wrapped prompt on top, ``box`` filling the middle, OK/Cancel at the bottom.

    Sizes are given at 96 dpi and scaled to the screen, because Revit is DPI-aware and
    raw pixel sizes look tiny and clip text on 125-200 % displays.
    """
    _load_winforms()
    from System.Drawing import Font, Size
    from System.Windows.Forms import (
        Button,
        DialogResult,
        DockStyle,
        FlowDirection,
        FlowLayoutPanel,
        Form,
        FormStartPosition,
        Label,
        Padding,
    )

    form = Form()
    factor = _dpi_factor(form)
    form.Text = title
    form.Font = Font(FONT_NAME, FONT_SIZE)
    height = COMPACT_HEIGHT if compact else BASE_HEIGHT
    form.Size = Size(scaled(BASE_WIDTH if not compact else COMPACT_WIDTH, factor), scaled(height, factor))
    form.MinimumSize = Size(scaled(MIN_WIDTH if not compact else COMPACT_WIDTH, factor), scaled(min(MIN_HEIGHT, height), factor))
    form.StartPosition = FormStartPosition.CenterScreen
    form.TopMost = True
    form.ShowInTaskbar = False

    header = Label()
    header.Text = prompt
    header.AutoSize = False
    header.Dock = DockStyle.Top
    header.Height = scaled(PROMPT_HEIGHT, factor)
    header.Padding = Padding(scaled(10, factor), scaled(8, factor), scaled(10, factor), scaled(4, factor))

    box.Dock = DockStyle.Fill
    if hasattr(box, "IntegralHeight"):
        box.IntegralHeight = False
        box.HorizontalScrollbar = True

    buttons = FlowLayoutPanel()
    buttons.Dock = DockStyle.Bottom
    buttons.FlowDirection = FlowDirection.RightToLeft
    buttons.Height = scaled(BUTTON_BAR_HEIGHT, factor)
    buttons.Padding = Padding(scaled(8, factor))

    cancel = Button()
    cancel.Text = "Cancel"
    cancel.DialogResult = DialogResult.Cancel
    accept = Button()
    accept.Text = button_text
    accept.DialogResult = DialogResult.OK
    for button in (cancel, accept):
        button.AutoSize = True
        button.MinimumSize = Size(scaled(BUTTON_WIDTH, factor), scaled(BUTTON_HEIGHT, factor))
        button.Padding = Padding(scaled(6, factor), 0, scaled(6, factor), 0)
    buttons.Controls.Add(cancel)
    buttons.Controls.Add(accept)
    form.AcceptButton = accept
    form.CancelButton = cancel

    # WinForms docks the last-added control first, so the fill control goes in last.
    form.Controls.Add(buttons)
    form.Controls.Add(header)
    form.Controls.Add(box)
    box.BringToFront()
    form.ActiveControl = box
    return form


def ask_text(title, prompt, default="", button_text="OK"):
    """Ask for one line of text. Returns the text, or None when cancelled."""
    _load_winforms()
    from System.Windows.Forms import DialogResult, TextBox
    box = TextBox()
    box.Text = default or ""
    form = _build_form(title, prompt, button_text, box, compact=True)
    try:
        trail_step("showing text box: {0}".format(title))
        if form.ShowDialog() != DialogResult.OK:
            return None
        return box.Text
    finally:
        form.Dispose()


def trail_step(text):
    try:
        import trail
        trail.step(text)
    except Exception:
        pass


def _load_winforms():
    import clr
    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")


def _dpi_factor(form):
    """Screen scale relative to 96 dpi, or 1.0 when it cannot be read."""
    try:
        dpi = float(form.DeviceDpi)
        if dpi > 0:
            return dpi / 96.0
    except Exception:
        pass
    try:
        from System import IntPtr
        from System.Drawing import Graphics
        graphics = Graphics.FromHwnd(IntPtr.Zero)
        try:
            return float(graphics.DpiX) / 96.0 or 1.0
        finally:
            graphics.Dispose()
    except Exception:
        return 1.0


def checked_indexes(preselected, count):
    """Return valid, unique, sorted indexes from ``preselected``."""
    return sorted(set(int(index) for index in (preselected or []) if 0 <= int(index) < count))


def pick_file(title, filter_text="JSON files (*.json)|*.json|All files (*.*)|*.*", initial_dir=None):
    """Return the chosen file path, or None when cancelled."""
    import clr
    clr.AddReference("System.Windows.Forms")
    from System.Windows.Forms import DialogResult, OpenFileDialog
    dialog = OpenFileDialog()
    dialog.Title = title
    dialog.Filter = filter_text
    dialog.CheckFileExists = True
    dialog.Multiselect = False
    if initial_dir:
        dialog.InitialDirectory = initial_dir
    try:
        if dialog.ShowDialog() == DialogResult.OK:
            return dialog.FileName
        return None
    finally:
        dialog.Dispose()
