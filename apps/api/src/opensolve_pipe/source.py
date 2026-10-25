"""The source of the running server (AGPL-3.0-or-later).

AGPL-3.0 §13 requires a network service to offer the users who interact with it the source of
the version they use. The web app links the commit it was built from (TSD §11.1), but the API
is built and deployed on its own and may run another commit, so the image records the commit
it is built from: the SOURCE_COMMIT build argument, which ``apps/api/cloudbuild.yaml`` requires
(TSD §11.2). The server reports it at ``/api/v1/about`` and redirects ``/source`` to it.

Anything but a full 40-character commit (unset in tests, a local ``docker build``) records no
commit; the links then point at the repository and its default branch, as the web app's do.
"""

import os
import re
from collections.abc import Mapping

REPOSITORY_URL = "https://github.com/ccirone2/opensolve-pipe"
LICENSE = "AGPL-3.0-or-later"

_COMMIT = re.compile(r"[0-9a-f]{40}")


def source_commit(environ: Mapping[str, str]) -> str | None:
    """The commit in ``SOURCE_COMMIT``, or None unless it is a full lowercase commit hash."""
    value = environ.get("SOURCE_COMMIT", "").strip()
    return value if _COMMIT.fullmatch(value) else None


def source_links(commit: str | None) -> tuple[str, str]:
    """The source tree and the license text at ``commit``, else at the default branch."""
    if commit is None:
        return REPOSITORY_URL, f"{REPOSITORY_URL}/blob/HEAD/LICENSE"
    return f"{REPOSITORY_URL}/tree/{commit}", f"{REPOSITORY_URL}/blob/{commit}/LICENSE"


COMMIT = source_commit(os.environ)
"""The commit this server was built from (None when the image does not record one)."""

SOURCE_URL, LICENSE_URL = source_links(COMMIT)
