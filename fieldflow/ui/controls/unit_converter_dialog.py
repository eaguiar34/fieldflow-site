from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton
)


def _f(s: str) -> float:
    try:
        return float((s or "").strip())
    except Exception:
        return 0.0


class UnitConverterDialog(QDialog):
    """
    Lightweight unit conversion helper for estimating.

    Conversions:
      - CY -> TON (density t/CY)
      - TON -> CY (density t/CY)
      - SY * thickness(in) -> TON (density t/CY, thickness default 3")
      - LF * width(ft) * depth(ft) -> CY
    """
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Unit Converter")
        self.resize(560, 220)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Quick conversions (transparent math). Adjust density/thickness as needed."))

        row = QHBoxLayout()
        self.cmb = QComboBox()
        self.cmb.addItems([
            "CY → TON (density t/CY)",
            "TON → CY (density t/CY)",
            "SY × thickness(in) → TON (density t/CY)",
            "LF × width(ft) × depth(ft) → CY",
        ])
        row.addWidget(self.cmb)
        layout.addLayout(row)

        self.inp_a = QLineEdit("0")
        self.inp_b = QLineEdit("0")
        self.inp_c = QLineEdit("0")

        layout.addWidget(QLabel("A (main quantity):"))
        layout.addWidget(self.inp_a)

        layout.addWidget(QLabel("B (density t/CY OR width ft):"))
        self.inp_b.setText("1.35")  # typical asphalt-ish per CY varies; user can change
        layout.addWidget(self.inp_b)

        layout.addWidget(QLabel("C (thickness in OR depth ft):"))
        self.inp_c.setText("3")
        layout.addWidget(self.inp_c)

        btns = QHBoxLayout()
        self.btn_calc = QPushButton("Calculate")
        self.btn_close = QPushButton("Close")
        btns.addWidget(self.btn_calc)
        btns.addStretch(1)
        btns.addWidget(self.btn_close)
        layout.addLayout(btns)

        self.out = QLabel("")
        layout.addWidget(self.out)

        self.btn_calc.clicked.connect(self._calc)
        self.btn_close.clicked.connect(self.accept)

        self.cmb.currentIndexChanged.connect(lambda _: self._set_defaults())

    def _set_defaults(self) -> None:
        i = self.cmb.currentIndex()
        if i in (0, 1):
            self.inp_b.setText("1.35")
            self.inp_c.setText("0")
        elif i == 2:
            self.inp_b.setText("1.35")
            self.inp_c.setText("3")
        else:
            self.inp_b.setText("4")  # width ft
            self.inp_c.setText("2")  # depth ft

    def _calc(self) -> None:
        i = self.cmb.currentIndex()
        a = _f(self.inp_a.text())
        b = _f(self.inp_b.text())
        c = _f(self.inp_c.text())

        if i == 0:
            tons = a * b
            self.out.setText(f"{a:,.3f} CY × {b:,.3f} t/CY = {tons:,.3f} TON")
        elif i == 1:
            cy = a / b if b else 0.0
            self.out.setText(f"{a:,.3f} TON ÷ {b:,.3f} t/CY = {cy:,.3f} CY")
        elif i == 2:
            # SY * thickness(in) -> CY then tons
            thickness_ft = c / 12.0
            cy = (a * 9.0 * thickness_ft) / 27.0
            tons = cy * b
            self.out.setText(f"{a:,.3f} SY @ {c:,.2f} in → {cy:,.3f} CY → {tons:,.3f} TON (density {b:,.3f} t/CY)")
        else:
            # LF * width * depth -> CY
            cuft = a * b * c
            cy = cuft / 27.0
            self.out.setText(f"{a:,.3f} LF × {b:,.3f} ft × {c:,.3f} ft = {cy:,.3f} CY")