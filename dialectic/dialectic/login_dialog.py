"""
Dialectic login dialog.

A modal PyQt6 dialog that collects Codex credentials, exchanges them
for an API key via ``credentials.login``, and reports success/failure
inline. Shown at startup when no valid credentials are stored.

The login call runs on a background thread so the UI stays responsive
— the POST to Vercel can take 1–3 seconds on first contact. The
dialog is blocked from dismissal while a request is in flight.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import credentials

log = logging.getLogger(__name__)


_DIALOG_QSS = """
QDialog#dialecticLogin {
    background-color: #0e0a06;
    color: #e3c995;
}
QDialog#dialecticLogin QLabel {
    color: #d4a017;
}
QDialog#dialecticLogin QLabel#titleLabel {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 5px;
    color: #d4a017;
}
QDialog#dialecticLogin QLabel#subtitleLabel {
    color: #a08868;
    font-size: 11px;
    font-style: italic;
}
QDialog#dialecticLogin QLabel#errorLabel {
    color: #c0392b;
    font-size: 11px;
}
QDialog#dialecticLogin QLineEdit {
    background-color: #15100a;
    color: #e3c995;
    border: 1px solid #3e2c13;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
    selection-background-color: #5a4218;
    selection-color: #f5e4c5;
}
QDialog#dialecticLogin QPushButton#signInBtn {
    background-color: #d4a017;
    color: #0e0a06;
    border: none;
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 3px;
}
QDialog#dialecticLogin QPushButton#signInBtn:hover {
    background-color: #efb82a;
}
QDialog#dialecticLogin QPushButton#signInBtn:disabled {
    background-color: #5a4218;
    color: #1a1309;
}
QDialog#dialecticLogin QPushButton#cancelBtn {
    background-color: transparent;
    color: #8a7352;
    border: 1px solid #3e2c13;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 11px;
    letter-spacing: 2px;
}
"""


class LoginDialog(QDialog):
    """Blocking login dialog. Exec this before opening the main window.

    On successful sign-in, ``self.credentials`` is populated and the
    dialog exits with ``Accepted``. On cancel or explicit quit, the
    caller should treat the return code as ``Rejected`` and exit the
    app (Dialectic requires authentication to run).
    """

    # Thread-safe signals for marshalling worker results back to the
    # Qt main thread. `QTimer.singleShot(0, callable)` was the previous
    # approach but QTimer is a QObject and must be created on the thread
    # that owns the event loop — if we construct one on the worker
    # thread, Qt silently refuses to fire it, so the "SIGNING IN…"
    # state would persist forever even on a successful POST. pyqtSignals
    # use Qt's cross-thread queued-connection machinery, which is
    # what we actually want.
    _login_succeeded = pyqtSignal(object)  # payload: StoredCredentials
    _login_failed = pyqtSignal(str)         # payload: user-safe message

    def __init__(
        self,
        *,
        prefill_url: str = credentials.DEFAULT_CODEX_URL,
        prefill_org: str = credentials.DEFAULT_ORG_SLUG,
        prefill_email: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dialecticLogin")
        self.setWindowTitle("Sign in to Dialectic")
        self.setStyleSheet(_DIALOG_QSS)
        self.setModal(True)
        self.setFixedWidth(440)

        self.credentials: Optional[credentials.StoredCredentials] = None
        self._in_flight = False

        # Wire the cross-thread signals to the main-thread handlers.
        # Default connection type = AutoConnection: since the receivers
        # live on the same thread the signals are connected on (the
        # Qt main thread), but emitted from a different thread, Qt
        # uses a queued connection automatically. That's exactly what
        # we need — the handlers run on the GUI thread.
        self._login_succeeded.connect(self._on_success)
        self._login_failed.connect(self._on_failure)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        title = QLabel("DIALECTIC")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel(
            "Sign in with your Theseus Codex credentials to enable\n"
            "recording, live analysis, and cloud upload."
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)

        # Form
        form = QFormLayout()
        form.setContentsMargins(0, 10, 0, 0)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._url_input = QLineEdit(prefill_url)
        self._url_input.setPlaceholderText(credentials.DEFAULT_CODEX_URL)

        self._org_input = QLineEdit(prefill_org)
        self._org_input.setPlaceholderText(credentials.DEFAULT_ORG_SLUG)

        self._email_input = QLineEdit(prefill_email)
        self._email_input.setPlaceholderText("you@example.com")

        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("••••••••")

        for label_text, widget in (
            ("Codex URL", self._url_input),
            ("Organization", self._org_input),
            ("Email", self._email_input),
            ("Passphrase", self._password_input),
        ):
            lbl = QLabel(label_text.upper())
            lbl.setFont(QFont("IBM Plex Mono", 9))
            lbl.setStyleSheet(
                "color: #a08868; font-size: 9pt; letter-spacing: 0.12em;"
            )
            form.addRow(lbl, widget)

        root.addLayout(form)

        self._error_label = QLabel("")
        self._error_label.setObjectName("errorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setVisible(False)
        root.addWidget(self._error_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Quit")
        self._cancel_btn.setObjectName("cancelBtn")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._sign_in_btn = QPushButton("SIGN IN")
        self._sign_in_btn.setObjectName("signInBtn")
        self._sign_in_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sign_in_btn.setDefault(True)
        self._sign_in_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self._sign_in_btn)

        root.addLayout(btn_row)

        # Prefill focus on email if empty, else password.
        QTimer.singleShot(
            0,
            lambda: (
                self._email_input.setFocus()
                if not prefill_email
                else self._password_input.setFocus()
            ),
        )

    def _set_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def _set_busy(self, busy: bool) -> None:
        self._in_flight = busy
        self._sign_in_btn.setEnabled(not busy)
        self._sign_in_btn.setText("SIGNING IN…" if busy else "SIGN IN")
        self._url_input.setEnabled(not busy)
        self._org_input.setEnabled(not busy)
        self._email_input.setEnabled(not busy)
        self._password_input.setEnabled(not busy)
        self._cancel_btn.setEnabled(not busy)

    def _on_submit(self) -> None:
        if self._in_flight:
            return
        url = self._url_input.text().strip()
        org = self._org_input.text().strip() or credentials.DEFAULT_ORG_SLUG
        email = self._email_input.text().strip()
        password = self._password_input.text()

        if not email or not password:
            self._set_error("Email and passphrase are both required.")
            return
        if not url.startswith("http://") and not url.startswith("https://"):
            self._set_error("Codex URL must start with http:// or https://")
            return

        self._set_error("")
        self._set_busy(True)

        def _do_login() -> None:
            # Worker thread: do the blocking HTTP POST, then emit one
            # of the two pyqtSignals to bounce the result back onto
            # the main thread. We specifically do NOT use
            # QTimer.singleShot here — QTimer is a QObject and must
            # be created on the thread that owns the event loop; a
            # timer constructed on this worker thread would never
            # fire, leaving the dialog "SIGNING IN…" forever even on
            # a successful round-trip (the actual bug we just fixed).
            try:
                creds = credentials.login(
                    codex_url=url,
                    organization_slug=org,
                    email=email,
                    password=password,
                )
                self._login_succeeded.emit(creds)
            except credentials.AuthError as e:
                self._login_failed.emit(str(e))
            except Exception as e:  # pragma: no cover — defensive
                log.exception("Unexpected login error")
                self._login_failed.emit(f"Unexpected error: {e}")

        threading.Thread(target=_do_login, daemon=True, name="DialecticLogin").start()

    def _on_success(self, creds: credentials.StoredCredentials) -> None:
        self.credentials = creds
        self._set_busy(False)
        self.accept()

    def _on_failure(self, message: str) -> None:
        self._set_busy(False)
        # Replay the password prompt; clear the field so the user doesn't
        # accidentally re-submit the same bad value on enter.
        self._password_input.clear()
        self._set_error(message)
        self._password_input.setFocus()


def ensure_authenticated(
    *,
    on_cancel: Optional[Callable[[], None]] = None,
) -> Optional[credentials.StoredCredentials]:
    """Return active credentials, launching the login dialog if needed.

    Call order:
      1. If the DIALECTIC_CLOUD_URL + _API_KEY env vars are set, those
         win — preserves the CI/script workflow (no UI prompt).
      2. If a credentials file exists, read + validate it. Offline
         (HTTP timeout / DNS fail) counts as valid-for-now.
      3. Otherwise show the login dialog. Returns credentials on
         success, or None if the user cancelled (caller should quit).
    """
    active = credentials.active()
    if active is not None:
        if credentials.validate(active):
            log.info(
                "credentials: resumed session for %s (%s)",
                active.founder_name or active.founder_email,
                active.codex_url,
            )
            return active
        # Stored token is bad (server said 401). Wipe it so the login
        # flow doesn't loop on a stale file.
        log.warning(
            "credentials: stored key rejected by %s/api/auth/whoami; clearing and re-prompting.",
            active.codex_url,
        )
        credentials.clear()

    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)

    prev = credentials.load()
    dialog = LoginDialog(
        prefill_url=(prev.codex_url if prev else credentials.DEFAULT_CODEX_URL),
        prefill_org=(
            prev.organization_slug if prev else credentials.DEFAULT_ORG_SLUG
        ),
        prefill_email=(prev.founder_email if prev else ""),
    )
    result = dialog.exec()
    if result == QDialog.DialogCode.Accepted and dialog.credentials is not None:
        return dialog.credentials

    if on_cancel is not None:
        on_cancel()
    return None
