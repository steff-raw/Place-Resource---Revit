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
    result = dialog.Show()
    for link_result, key in results:
        if result == link_result:
            return key
    return None


def ask_yes_no(title, instruction, content=None, yes_label="Yes", no_label="No"):
    """Return True only when the user picks the first option."""
    choice = choose_command(title, instruction, [("yes", yes_label), ("no", no_label)], content=content)
    return choice == "yes"


def choose_from_list(title, labels, prompt=None, button_text="Select"):
    """Pick one entry from a filterable list. Returns its index, or None when cancelled."""
    labels = [str(label) for label in labels]
    if not labels:
        return None
    import clr
    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    from System.Drawing import Size
    from System.Windows.Forms import (
        Button,
        DialogResult,
        DockStyle,
        FlowDirection,
        FlowLayoutPanel,
        Form,
        FormStartPosition,
        Label,
        ListBox,
        TextBox,
    )

    form = Form()
    form.Text = title
    form.Size = Size(560, 460)
    form.MinimumSize = Size(360, 260)
    form.StartPosition = FormStartPosition.CenterScreen
    form.TopMost = True
    form.ShowInTaskbar = False

    header = Label()
    header.Text = prompt or "Type to filter, then select one item."
    header.Dock = DockStyle.Top
    header.Height = 24

    search = TextBox()
    search.Dock = DockStyle.Top

    box = ListBox()
    box.Dock = DockStyle.Fill
    box.IntegralHeight = False

    buttons = FlowLayoutPanel()
    buttons.Dock = DockStyle.Bottom
    buttons.FlowDirection = FlowDirection.RightToLeft
    buttons.Height = 40

    cancel = Button()
    cancel.Text = "Cancel"
    cancel.DialogResult = DialogResult.Cancel
    accept = Button()
    accept.Text = button_text
    accept.DialogResult = DialogResult.OK
    buttons.Controls.Add(cancel)
    buttons.Controls.Add(accept)
    form.AcceptButton = accept
    form.CancelButton = cancel

    visible = []

    def _refill(text):
        needle = (text or "").strip().lower()
        box.BeginUpdate()
        box.Items.Clear()
        del visible[:]
        for index, label in enumerate(labels):
            if needle and needle not in label.lower():
                continue
            visible.append(index)
            box.Items.Add(label)
        box.EndUpdate()
        if box.Items.Count:
            box.SelectedIndex = 0

    def _on_search(sender, args):
        _refill(search.Text)

    def _on_double_click(sender, args):
        if box.SelectedIndex >= 0:
            form.DialogResult = DialogResult.OK
            form.Close()

    search.TextChanged += _on_search
    box.DoubleClick += _on_double_click

    # WinForms docks the last-added control first, so the fill control goes in last.
    form.Controls.Add(buttons)
    form.Controls.Add(search)
    form.Controls.Add(header)
    form.Controls.Add(box)
    box.BringToFront()
    _refill("")
    form.ActiveControl = search

    try:
        result = form.ShowDialog()
        if result != DialogResult.OK or box.SelectedIndex < 0:
            return None
        return visible[box.SelectedIndex]
    finally:
        form.Dispose()


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
