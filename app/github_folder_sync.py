import argparse
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

import requests


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now_str()}] {msg}", flush=True)


def parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """
    Parse GitHub URL and return (owner, repo).
    Supports:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
    """
    https_match = re.match(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url.strip())
    if https_match:
        return https_match.group(1), https_match.group(2)

    ssh_match = re.match(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", repo_url.strip())
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)

    raise ValueError(f"GitHub URL khong hop le: {repo_url}")


def build_headers(token: Optional[str]) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-folder-sync-script",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_get_json(url: str, headers: Dict[str, str], timeout: int = 30):
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"GitHub API error {resp.status_code}: {resp.text}")
    return resp.json()


def get_default_branch(owner: str, repo: str, headers: Dict[str, str]) -> str:
    repo_api = f"https://api.github.com/repos/{owner}/{repo}"
    data = github_get_json(repo_api, headers)
    branch = data.get("default_branch")
    if not branch:
        raise RuntimeError("Khong lay duoc default_branch tu GitHub API")
    return branch


def list_remote_root_folders(owner: str, repo: str, branch: str, headers: Dict[str, str]) -> List[str]:
    contents_api = f"https://api.github.com/repos/{owner}/{repo}/contents?ref={branch}"
    data = github_get_json(contents_api, headers)

    if not isinstance(data, list):
        raise RuntimeError("Du lieu contents API khong dung dinh dang")

    folders = [item["name"] for item in data if item.get("type") == "dir"]
    folders.sort()
    return folders


def list_local_folders(local_root: str) -> List[str]:
    if not os.path.isdir(local_root):
        raise RuntimeError(f"Thu muc local khong ton tai: {local_root}")

    folders = []
    for name in os.listdir(local_root):
        full_path = os.path.join(local_root, name)
        if os.path.isdir(full_path):
            folders.append(name)
    folders.sort()
    return folders


def download_file(download_url: str, dest_path: str, headers: Dict[str, str], timeout: int = 60) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    resp = requests.get(download_url, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Khong tai duoc file {download_url}. HTTP {resp.status_code}")
    with open(dest_path, "wb") as f:
        f.write(resp.content)


def download_directory_recursive(
    owner: str,
    repo: str,
    branch: str,
    remote_dir_path: str,
    local_root: str,
    headers: Dict[str, str],
) -> None:
    """
    Download a directory from GitHub repo recursively.
    remote_dir_path is path in repo, e.g. "folderA" or "folderA/subB".
    """
    contents_api = f"https://api.github.com/repos/{owner}/{repo}/contents/{remote_dir_path}?ref={branch}"
    data = github_get_json(contents_api, headers)

    if not isinstance(data, list):
        raise RuntimeError(f"Path khong phai folder: {remote_dir_path}")

    for item in data:
        item_type = item.get("type")
        item_name = item.get("name")
        item_path = item.get("path")

        if not item_type or not item_name or not item_path:
            continue

        if item_type == "dir":
            download_directory_recursive(owner, repo, branch, item_path, local_root, headers)
        elif item_type == "file":
            download_url = item.get("download_url")
            if not download_url:
                continue
            dest_path = os.path.join(local_root, item_path.replace("/", os.sep))
            download_file(download_url, dest_path, headers)
        else:
            # skip symlink/submodule/unknown
            continue


def sync_once(local_root: str, owner: str, repo: str, branch: str, headers: Dict[str, str]) -> None:
    remote_folders = list_remote_root_folders(owner, repo, branch, headers)
    local_folders = list_local_folders(local_root)

    remote_set = set(remote_folders)
    local_set = set(local_folders)
    new_folders = sorted(remote_set - local_set)

    log(f"Remote folders: {len(remote_folders)} | Local folders: {len(local_folders)}")

    if not new_folders:
        log("Khong co folder moi tren GitHub")
        return

    log(f"Phat hien {len(new_folders)} folder moi: {new_folders}")
    for folder in new_folders:
        log(f"Dang tai folder: {folder}")
        download_directory_recursive(owner, repo, branch, folder, local_root, headers)
        log(f"Da tai xong: {folder}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dong bo folder moi tu GitHub repo ve local folder moi 60 giay"
    )
    parser.add_argument("local_folder", help="Duong dan folder local de luu")
    parser.add_argument("repo_url", help="Link GitHub repo")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Chu ky dong bo (giay), mac dinh 60",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Nhanh can theo doi. Neu bo trong se dung default_branch cua repo",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN"),
        help="GitHub token (hoac dat qua env GITHUB_TOKEN)",
    )
    args = parser.parse_args()

    local_root = os.path.abspath(args.local_folder)
    owner, repo = parse_repo_url(args.repo_url)
    headers = build_headers(args.token)

    if not os.path.isdir(local_root):
        os.makedirs(local_root, exist_ok=True)

    branch = args.branch or get_default_branch(owner, repo, headers)
    log(f"Start sync: {owner}/{repo} | branch={branch} | local={local_root}")

    while True:
        try:
            sync_once(local_root, owner, repo, branch, headers)
        except Exception as exc:
            log(f"Loi khi dong bo: {exc}")

        log(f"Sleep {args.interval} giay")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
