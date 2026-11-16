"""Compare event commits; only a branch-creation push may use default merge-base."""
import os
import re
import subprocess


def git(*args):
    return subprocess.check_output(["git", "--no-pager", *args], text=True).strip()


def commit(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected an exact commit SHA")
    git("cat-file", "-e", value + "^{commit}")
    return value


def main():
    base, head = os.environ["BASE"], commit(os.environ["HEAD"])
    event = os.environ["EVENT_NAME"]
    if event == "push" and base == "0" * 40:
        branch = os.environ["DEFAULT_BRANCH"]
        git("check-ref-format", "refs/heads/" + branch)
        # Explicit refspec, not an ambient/stale remote-tracking ref.
        ref = "refs/whitespace/default"
        git("fetch", "--no-tags", "origin", "+refs/heads/" + branch + ":" + ref)
        default = commit(git("rev-parse", "--verify", ref))
        base = commit(git("merge-base", default, head))
    elif event not in ("push", "pull_request"):
        raise ValueError("Unsupported event")
    else:
        base = commit(base)
    subprocess.run(["git", "--no-pager", "diff", "--check", base, head], check=True)


if __name__ == "__main__":
    main()
