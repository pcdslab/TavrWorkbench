"""Approve / Flag radio-button tables (one row per label) and button-group helpers."""
import qt

from .constants import RATING_ACCEPT, RATING_FLAG, RATING_NONE

BUTTON_ID = {RATING_ACCEPT: 1, RATING_FLAG: 2}
ID_TO_RATING = {v: k for k, v in BUTTON_ID.items()}


def uncheck_group(group):
    group.setExclusive(False)
    for b in group.buttons():
        b.setChecked(False)
    group.setExclusive(True)


def set_group_rating(group, rating):
    bid = BUTTON_ID.get(rating)
    if bid:
        group.button(bid).setChecked(True)
    else:
        uncheck_group(group)


def group_rating(group):
    return ID_TO_RATING.get(group.checkedId(), RATING_NONE)


def make_decision_group(approve_radio, flag_radio):
    """Exclusive group for an Approve / Flag pair (ids match the rating tables)."""
    group = qt.QButtonGroup()
    group.addButton(approve_radio, BUTTON_ID[RATING_ACCEPT])
    group.addButton(flag_radio, BUTTON_ID[RATING_FLAG])
    return group


class RatingTable:
    """A group box with one ✓ / ⚑ row per label, built inside `container`."""

    def __init__(self, container, title, first_column):
        self._container = container
        self._title = title
        self._first_column = first_column
        self._layout = qt.QVBoxLayout(container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._box = None
        self.groups = {}

    def build(self, labels):
        if self._box is not None:
            self._layout.removeWidget(self._box)
            self._box.setParent(None)
            self._box.deleteLater()
        self._box, self.groups = None, {}
        self._container.setVisible(bool(labels))
        if not labels:
            return

        box = qt.QGroupBox(self._title)
        grid = qt.QGridLayout(box)
        grid.addWidget(qt.QLabel(f"<b>{self._first_column}</b>"), 0, 0)
        grid.addWidget(qt.QLabel("<b>✓</b>"), 0, 1, qt.Qt.AlignCenter)
        grid.addWidget(qt.QLabel("<b>⚑</b>"), 0, 2, qt.Qt.AlignCenter)
        for row, label in enumerate(labels, start=1):
            grid.addWidget(qt.QLabel(label), row, 0)
            group = qt.QButtonGroup(box)
            for rating, col in ((RATING_ACCEPT, 1), (RATING_FLAG, 2)):
                rb = qt.QRadioButton()
                group.addButton(rb, BUTTON_ID[rating])
                grid.addWidget(rb, row, col, qt.Qt.AlignCenter)
            self.groups[label] = group
        self._layout.addWidget(box)
        self._box = box

    def set_all(self, rating):
        for group in self.groups.values():
            set_group_rating(group, rating)

    def clear(self):
        for group in self.groups.values():
            uncheck_group(group)

    def set_ratings(self, stored):
        for label, group in self.groups.items():
            set_group_rating(group, (stored or {}).get(label, RATING_NONE))

    def ratings(self):
        return {label: group_rating(group) for label, group in self.groups.items()}
