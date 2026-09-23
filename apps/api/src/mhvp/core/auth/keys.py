"""``python -m mhvp.core.auth.keys``: print new values for MHVP_MASTER_KEY and MHVP_JWT_PRIVATE_KEY.

Store them in the secret store of the environment (.env, Vaultwarden/SOPS), never in the repo.
"""

import base64
import os
import sys

from mhvp.core.auth.tokens import generate_private_key_pem


def main() -> int:
    master = base64.b64encode(os.urandom(32)).decode()
    pem = generate_private_key_pem().strip().replace("\n", "\\n")
    sys.stdout.write(f'MHVP_MASTER_KEY={master}\nMHVP_JWT_PRIVATE_KEY="{pem}"\n')
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
