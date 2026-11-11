# BKOMIK Ludo Master

A single-file Python/Kivy Ludo game designed to run in **Pydroid 3 on Android**.

## Features in this source build

- Local games with human and computer-controlled players.
- Easy, Medium and Hard computer difficulty.
- Two-player local Wi-Fi/LAN mode (RED host, GREEN guest) using TCP port `5050` and a six-digit room code.
- Automatic token movement when exactly one legal move exists.
- Turn passing when no legal move exists, and an extra turn after rolling six.
- Captures, safe squares, home lanes and exact-finish rules.
- Local statistics, match history, leaderboard, achievements and daily challenge.
- Optional sound effects.

**Multiplayer scope:** LAN only. Both phones must be on the same reachable Wi-Fi network. This build does not provide internet matchmaking, cloud accounts, cloud saves or cloud leaderboards.

## Run on Pydroid 3

1. Install **Pydroid 3** on the Android device.
2. In Pydroid 3, open its Pip section and install `kivy` if it is not already installed.
3. Copy `main.py` to a folder on the device.
4. Open `main.py` in Pydroid 3 and press Run.
5. Allow the Android network permission prompt if shown.

For LAN play, start **LAN MULTIPLAYER - HOST** on one phone. Give the guest the host IP address and six-digit room code. On the second phone, choose **LAN MULTIPLAYER - JOIN** and enter both values. Keep both phones on the same Wi-Fi network and ensure the router does not isolate wireless clients.

If the guest disconnects, the host keeps its room listener open; the guest can try joining again with the same IP and room code. The guest currently needs to initiate that reconnect manually.

## Project files

- `main.py` — application source.
- `requirements.txt` — Python package dependency for Pydroid 3.
- `buildozer.spec` — starter configuration for a Linux/WSL Android build.
- `tests/test_release_checks.py` — source-level and persistence helper tests.
- `RELEASE_TEST_PLAN.md` — manual device test plan and known limitations.
- `PRIVACY_POLICY_DRAFT.md` — draft only; complete and host before any public release.

## Checks performed in this package

- Python bytecode compilation (`python -m py_compile main.py`).
- Unit tests for statistics loading/saving and source-level release invariants.

Kivy UI rendering, gameplay animation, Wi-Fi socket behaviour and Android lifecycle have **not** been validated on physical Android devices in this environment. Complete the manual test plan before treating this as a production release.

## Android APK/AAB packaging

Buildozer is intended to run from Linux (for example Ubuntu or WSL), not ordinary Pydroid 3. The included `buildozer.spec` is a starter configuration. Use a unique package identifier that you control, check the current Google Play target API requirements, create and securely back up your signing key, then build and test an APK/AAB. No signed APK or AAB is included in this source package.

## GitHub

Repository target: <https://github.com/bonifacemunala7/Bkomik-ludo-master1>

Upload the contents of this folder to the repository root on the `main` branch. Do not upload signing keys, passwords, API tokens, private user data, or generated local statistics.
