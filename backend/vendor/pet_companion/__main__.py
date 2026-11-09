from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from pet_memory.providers import from_environment
from pet_memory.types import MemoryError, dumps
from .demo import run_demo, seed_demo
from .models import CoreError, require
from .providers import configured_model
from .runtime import CompanionRuntime


def dispatch(runtime, request):
    require(isinstance(request, dict), "invalid_request", "请求必须为对象")
    require(set(request) <= {"id", "protocol", "method", "params"}, "invalid_request", "请求包含未知字段；进程归属由启动配置固定")
    require(request.get("protocol", "companion.v1") == "companion.v1", "invalid_protocol", "协议版本不兼容")
    methods = {"send": runtime.send, "acknowledge": runtime.acknowledge, "interrupt": runtime.interrupt,
               "pause": runtime.pause, "new_session": runtime.new_session, "retry": runtime.retry,
               "status": runtime.status, "poll": runtime.poll, "history": runtime.history,
               "set_profile": runtime.set_profile, "remember": runtime.remember,
               "forget_memory": runtime.forget_memory, "correct_memory": runtime.correct_memory,
               "audio_started": runtime.audio_started, "mouth": runtime.mouth}
    method, params = request.get("method"), request.get("params", {})
    require(isinstance(method, str) and method in methods and isinstance(params, dict), "invalid_request", "方法或参数无效")
    try:
        return methods[method](**params)
    except TypeError:
        raise CoreError("invalid_parameters", "参数缺失或包含未知字段") from None


def serve(runtime):
    while True:
        raw = sys.stdin.buffer.readline(1_000_002)
        if not raw:
            return
        rid = None
        try:
            require(len(raw) <= 1_000_000 and raw.endswith(b"\n"), "invalid_request", "请求过大或缺少换行")
            request = json.loads(raw.decode("utf-8-sig"))
            rid = request.get("id") if isinstance(request, dict) else None
            require(rid is None or isinstance(rid, (str, int)), "invalid_request", "id 无效")
            result = dispatch(runtime, request)
            response = {"id": rid, "ok": True, "result": result}
        except MemoryError as exc:
            response = {"id": rid, "ok": False, "error": {"code": exc.code, "message": str(exc)}}
        except (ValueError, UnicodeError):
            response = {"id": rid, "ok": False, "error": {"code": "invalid_json", "message": "请求须为有效 UTF-8 JSON"}}
        except Exception:
            response = {"id": rid, "ok": False, "error": {"code": "internal_error", "message": "本次操作未完成"}}
        print(dumps(response), flush=True)


def console(runtime):
    print("桌宠联动组件 0.1.0，当前模式：" + runtime.model.mode)
    print("输入消息开始交流；/打断 /状态 /记住 内容 /退出")
    while True:
        try:
            text = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        try:
            if text == "/退出":
                return
            if text == "/打断":
                runtime.interrupt()
            elif text == "/状态":
                print(dumps(runtime.status()))
            elif text.startswith("/记住 "):
                print(dumps(runtime.remember(text[4:])))
            elif text:
                result = runtime.send(text)
                cursor = 0
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    batch = runtime.poll(cursor)
                    cursor = batch["next_cursor"]
                    found = False
                    for event in batch["events"]:
                        if event["turn_id"] != result["turn_id"]:
                            continue
                        if event["type"] == "reply.ready":
                            p = event["payload"]
                            if runtime.can_present(event["turn_id"], p["generation"]):
                                print("\n" + runtime.profile.name + "> " + p["plan"]["text"])
                                runtime.acknowledge(event["turn_id"], p["generation"], len(p["plan"]["text"]), completed=True)
                            else:
                                runtime.interrupt("stale_context")
                                print("记忆已更新，请再发送这条消息。")
                            found = True
                        elif event["type"] == "turn.failed":
                            print("这轮未完成：" + event["payload"]["code"])
                            found = True
                    if found:
                        break
                    time.sleep(0.02)
                else:
                    runtime.interrupt("console_timeout")
                    print("本轮已超时并停止。")
        except MemoryError as exc:
            print(f"未完成：{exc}")


def main():
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="独立桌宠联动组件")
    parser.add_argument("command", nargs="?", choices=["gui", "console", "serve", "demo"], default="gui")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--providers", action="store_true", help="启用显式配置的聊天模型")
    parser.add_argument("--memory-providers", action="store_true", help="启用显式配置的记忆提取与嵌入模型")
    parser.add_argument("--demo", action="store_true", help="使用独立演示数据与虚构资料")
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profile", type=Path, help="仅用于首次创建的角色设定文件")
    args = parser.parse_args()
    demo = args.demo or args.command == "demo"
    path = args.data_dir or os.getenv("PET_COMPANION_DATA_DIR") or Path(__file__).resolve().parent.parent / "data" / ("demo" if demo else "local")
    try:
        model = configured_model() if args.providers else None
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig")) if args.profile else None
        with CompanionRuntime(path, profile=profile, model=model,
                              memory_options=from_environment() if args.memory_providers else None) as runtime:
            if args.command == "demo":
                run_demo(runtime)
            elif args.command == "serve":
                if demo:
                    seed_demo(runtime)
                serve(runtime)
            elif args.command == "console":
                if demo:
                    seed_demo(runtime)
                console(runtime)
            else:
                from .ui import Workbench
                if demo:
                    seed_demo(runtime)
                app = Workbench(runtime)
                if args.smoke:
                    app.root.after(100, lambda: app.send("你还记得观测站吗"))
                    if os.getenv("PET_COMPANION_SMOKE_REPORT"):
                        def report_smoke():
                            visible = bool(app.root.winfo_viewable())
                            if os.name == "nt":
                                import ctypes
                                hwnd = ctypes.windll.user32.GetParent(app.root.winfo_id())
                                visible = bool(ctypes.windll.user32.IsWindowVisible(hwnd))
                            report = {"window_visible": visible, "input_visible": bool(app.input.winfo_ismapped()),
                                      "send_button_visible": bool(app.send_button.winfo_ismapped()),
                                      "reply_delivered": any(r["status"] == "completed" for r in runtime.history()),
                                      "mode": runtime.model.mode}
                            Path(os.environ["PET_COMPANION_SMOKE_REPORT"]).write_text(dumps(report), encoding="utf-8")
                        app.root.after(1450, report_smoke)
                    app.root.after(1600, app.close)
                app.root.mainloop()
    except MemoryError as exc:
        if sys.stderr:
            print(dumps({"error": {"code": exc.code, "message": str(exc)}}), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        if sys.stderr:
            print("配置或数据文件未能读取，请检查路径。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
