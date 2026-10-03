"""Install hints shown when an optional extra is missing. One wording everywhere: a bare
`uv sync --extra X` removes the other extras, so always recommend installing them together."""

INSTALL_EXTRAS = "uv sync --all-extras (или uv sync --extra prep --extra ui)"
NEED_PREP = f"Нужен пакет omnivoice[prep]: {INSTALL_EXTRAS}"
NEED_UI = f"Нужен пакет omnivoice[ui]: {INSTALL_EXTRAS}"
