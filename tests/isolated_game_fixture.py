"""Run SDK acceptance cases against a fresh, loopback-only NeoForge world.

Explicit dependencies are read-only inputs. No production world, whitelist,
credentials or provisioning service is used. Each invocation requires a new
directory, retains logs/evidence, and stops its own JVM on every exit path.
This fixture deliberately does not prove real-player login or production load.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid

SOURCE = Path(__file__).resolve().parents[1]
AREA = {"dimension": "minecraft:overworld", "min": [-24, 60, -24], "max": [24, 78, 24]}
OWNER = {"name": "FixtureOwner", "uuid": str(uuid.uuid5(uuid.NAMESPACE_DNS, "scrucraft.fixture.owner"))}


def wait_for(predicate, timeout=15, description="condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise TimeoutError(description)


class Fixture:
    def __init__(self, args):
        self.args = args
        self.root = args.directory.resolve()
        if self.root.exists():
            raise ValueError("Use a new fixture directory; existing directories are never overwritten")
        self.root.mkdir(parents=True, mode=0o700)
        self.server = self.root / "server"
        (self.server / "mods").mkdir(parents=True)
        (self.server / "config").mkdir()
        self.process = None
        self.ws = None
        self.gateway = None
        self.log = None
        self.evidence = {"schema": 1, "fixture": "isolated_neoforge", "synthetic_identity": True,
                         "production_world_used": False, "cases": [], "started_at": time.time()}
        # Fingerprint the Python actually imported by this run, independently of
        # later edits or repackaging of the development checkout.
        sources = [p for directory in ('sdk/scru_minecraft', 'agent-gateway', 'tests')
                   for p in (SOURCE / directory).glob('*.py')]
        self.evidence['python_source_sha256'] = {
            p.relative_to(SOURCE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(sources)}

    def console(self, command):
        if "\n" in command or "\r" in command:
            raise ValueError("One fixture console command per call")
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Fixture JVM is not running")
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def start(self):
        args = self.args
        libraries = args.libraries.resolve(strict=True)
        argfile = libraries / "net/neoforged/neoforge/21.1.265/unix_args.txt"
        if not argfile.is_file():
            raise ValueError("NeoForge 21.1.265 Unix libraries required")
        (self.server / "libraries").symlink_to(libraries, target_is_directory=True)
        for artifact in (args.adapter, args.luckperms):
            source = artifact.resolve(strict=True)
            shutil.copyfile(source, self.server / "mods" / source.name)
        self.evidence["adapter_sha256"] = hashlib.sha256(args.adapter.read_bytes()).hexdigest()
        (self.server / "eula.txt").write_text("eula=true\n")
        properties = {
            "server-ip": "127.0.0.1", "server-port": str(args.game_port), "online-mode": "false",
            "enforce-secure-profile": "false", "enable-rcon": "false", "enable-query": "false",
            "level-name": "fixture-world", "level-type": "minecraft:flat", "generate-structures": "false",
            "generator-settings": json.dumps({"layers": [{"block": "minecraft:bedrock", "height": 1},
                {"block": "minecraft:dirt", "height": 61}, {"block": "minecraft:stone", "height": 2}],
                "biome": "minecraft:plains", "features": False, "lakes": False}),
            "difficulty": "normal", "gamemode": "survival", "spawn-protection": "0", "max-players": "12",
            "view-distance": "2", "simulation-distance": "2", "sync-chunk-writes": "false",
            "motd": "SCRUCraft isolated API verification", "max-tick-time": "60000",
        }
        (self.server / "server.properties").write_text("".join(f"{key}={value}\n" for key, value in properties.items()))
        (self.server / "config/syn-agents.json").write_text('{"agents": []}\n')
        service = self.root / "agent-service"
        service.mkdir(mode=0o700)
        token_path = service / "fixture.token"
        token_path.write_text(secrets.token_urlsafe(32))
        token_path.chmod(0o600)
        (service / "gateway.json").write_text(json.dumps({"control_transport": "websocket",
            "token_file": str(token_path), "websocket_url": f"ws://127.0.0.1:{args.ws_port}/internal/body"}))
        config = self.root / "fixture-gateway.json"
        config.write_text(json.dumps({"name_prefix_required": False, "internal_token_file": str(token_path),
            "provision_socket": "unused-isolated-fixture", "websocket_enabled": True}))
        sys.path.insert(0, str(SOURCE / "agent-gateway"))
        sys.path.insert(0, str(SOURCE / "sdk"))
        import gateway
        import streaming
        self.members = [dict(OWNER)]

        def identity(value):
            if value["operation"] != "whitelist":
                raise ValueError("Real enrollment is outside this synthetic fixture")
            return {"ok": True, "members": self.members}

        def provision(operation, name, job, socket):
            if operation not in {"spawn", "remove"} or not gateway.NAME.fullmatch(name) or job not in gateway.JOBS:
                raise ValueError("Invalid fixture provisioning")
            self.console(f"synagent {operation} {name}" + (f" {job}" if operation == "spawn" else ""))
            return {"ok": True}

        self.gateway = gateway.Gateway(self.root / "gateway", config, identity_fn=identity, provision_fn=provision)
        self.ws = streaming.make_server(self.gateway, host="127.0.0.1", port=args.ws_port)
        threading.Thread(target=self.ws.serve_forever, daemon=True).start()
        self.log = (self.root / "minecraft.log").open("w")
        self.process = subprocess.Popen(["java", "-Xms512M", "-Xmx1536M", "-XX:+UseG1GC",
            "-XX:ActiveProcessorCount=2", "@libraries/net/neoforged/neoforge/21.1.265/unix_args.txt", "nogui"],
            cwd=self.server, stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT, text=True)

        def ready():
            if self.process.poll() is not None:
                raise RuntimeError(f"Fixture JVM exited {self.process.returncode}; inspect minecraft.log")
            return 'For help, type "help"' in (self.root / "minecraft.log").read_text(errors="replace")

        wait_for(ready, 180, "Fixture server startup")
        for command in ["gamerule doMobSpawning false", "gamerule doDaylightCycle false", "time set day",
                        "gamerule spawnRadius 0", "setworldspawn 0 64 0", "gamerule doWeatherCycle false",
                        "weather clear", "gamerule keepInventory true"]:
            self.console(command)
        self.evidence["jvm_pid"] = self.process.pid
        return self

    def client(self, name="VerifyBuilder", area=None):
        from scru_minecraft import AgentClient
        with self.gateway.changed:
            player = self.gateway.issue(OWNER["name"], "player", player_uuid=OWNER["uuid"])
            self.gateway.handle("POST", "/v1/agents", {"Authorization": "Bearer " + player},
                                {"name": name, "job": "engineer", "area": area or AREA})
            token = self.gateway.issue(OWNER["name"], "agent", name, player_uuid=OWNER["uuid"])
        wait_for(lambda: self.gateway.frames.get(name, {}).get("body_epoch"), 40, "Body bridge readiness")
        self.console(f"tp {name} 0.5 64 0.5")
        time.sleep(.25)
        return AgentClient(f"http://127.0.0.1:{self.args.ws_port}", token, name, allow_local_http=True, timeout=8)

    def case(self, name, checklist_ids, run):
        started = time.monotonic()
        try:
            result = run() or {}
            row = {"name": name, "checklist_ids": checklist_ids, "status": "passed", "evidence": result}
        except Exception as error:
            row = {"name": name, "checklist_ids": checklist_ids, "status": "failed",
                   "error": type(error).__name__ + ": " + str(error),
                   "failure_at": [{"file": Path(frame.filename).name, "line": frame.lineno,
                                   "function": frame.name}
                                  for frame in traceback.extract_tb(error.__traceback__)]}
        row["seconds"] = round(time.monotonic() - started, 3)
        self.evidence["cases"].append(row)
        self.write_evidence()
        print(json.dumps(row), flush=True)
        return row["status"] == "passed"

    def write_evidence(self):
        (self.root / "evidence.json").write_text(json.dumps(self.evidence, indent=2) + "\n")

    def close(self):
        if self.process and self.process.poll() is None:
            try:
                self.console("stop")
                self.process.wait(timeout=30)
            except (TimeoutError, subprocess.TimeoutExpired, OSError):
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        if self.ws:
            self.ws.shutdown()
        if self.gateway:
            self.gateway.db.close()
        if self.log:
            self.log.close()
        self.evidence["finished_at"] = time.time()
        self.evidence["jvm_stopped"] = not self.process or self.process.poll() is not None
        self.write_evidence()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--libraries", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--luckperms", type=Path, required=True)
    parser.add_argument("--game-port", type=int, default=18565)
    parser.add_argument("--ws-port", type=int, default=18769)
    parser.add_argument("--performance-seconds", type=int, default=0)
    args = parser.parse_args()
    fixture = Fixture(args)
    try:
        fixture.start()
        from gameplay_cases import run_cases
        run_cases(fixture)
        if args.performance_seconds:
            from performance_gameplay_cases import run_cases as performance_cases
            performance_cases(fixture, seconds=args.performance_seconds)
        return int(any(row["status"] != "passed" for row in fixture.evidence["cases"]))
    finally:
        fixture.close()


if __name__ == "__main__":
    raise SystemExit(main())
