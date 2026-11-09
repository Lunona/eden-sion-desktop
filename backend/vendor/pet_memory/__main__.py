from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from .core import MemoryService
from .providers import from_environment
from .types import MemoryError, Scope, dumps, require


def dispatch(service: MemoryService, request: dict):
    require(isinstance(request, dict), "invalid_request", "请求必须是 JSON 对象")
    require(request.get("protocol", "memory.v1") == "memory.v1", "protocol_version", "协议版本不兼容")
    method = request.get("method")
    params = request.get("params", {})
    require(isinstance(params, dict), "invalid_request", "params 必须是对象")
    methods = {"observe": service.observe, "remember": service.remember, "recall": service.recall,
               "correct": service.correct, "forget": service.forget, "inspect": service.inspect,
               "set_identity": service.set_identity, "identity": service.identity,
               "add_alias": service.add_alias, "export": service.export, "import": service.import_data,
               "health": service.health, "reindex": service.reindex, "jobs": service.jobs}
    if method == "maintain":
        require(set(params) <= {"limit", "retry_failed", "ready_only"}, "invalid_request", "维护参数无效")
        return service.process_pending(**params)
    require(method in methods, "unknown_method", "未知方法")
    s = Scope.parse(request.get("scope"))
    try:
        return methods[method](s, **params)
    except TypeError:
        raise MemoryError("invalid_parameters", "方法参数不完整或包含未知字段") from None


def serve(service):
    service.start_worker()
    while True:
        raw = sys.stdin.buffer.readline(1_000_002)
        if not raw:
            break
        request_id = None
        try:
            require(len(raw) <= 1_000_000 and raw.endswith(b"\n"), "request_too_large", "单行请求过大或缺少换行")
            request = json.loads(raw.decode("utf-8-sig"))
            if isinstance(request, dict):
                request_id = request.get("id")
                require(request_id is None or isinstance(request_id, (str, int)), "invalid_request", "请求 id 无效")
            result = dispatch(service, request)
            output = {"id": request_id, "ok": True, "result": result}
        except MemoryError as exc:
            output = {"id": request_id, "ok": False, "error": {"code": exc.code, "message": str(exc)}}
        except (ValueError, UnicodeError):
            output = {"id": request_id, "ok": False, "error": {"code": "invalid_json", "message": "请求不是有效 UTF-8 JSON"}}
        except Exception:
            output = {"id": request_id, "ok": False, "error": {"code": "internal_error", "message": "本次操作未完成"}}
        print(dumps(output), flush=True)


def demo(service):
    s = Scope("example-user", "example-character", ("real", "canon:example", "branch:example"))
    identity = service.identity(s)
    if identity["profile"] is None:
        service.set_identity(s, {"name": "示例角色", "origin": "虚构的示例作品", "knows_origin": True,
            "self_description": "我知道自己来自故事，也知道现在正在通过桌宠与你交流。原作过往和我们的新经历都属于我的记忆。",
            "visible_world_ids": list(s.visible_world_ids), "story_progress": {"canon:example": 2}})
    memories = [
        ("demo-canon", "在原作第二章，我和朋友一起修好了山上的观测站。", "canon:example", "canon", "document", {"chapter": 2}),
        ("demo-shared", "昨天我们聊过原作里的观测站，你说喜欢那一段。", "real", "shared_experience", "user", {}),
        ("demo-preference", "你希望我叫你小林。", "real", "shared_experience", "user", {})]
    for key, text, world, layer, role, qualifiers in memories:
        service.remember(s, text, world_id=world, knowledge_layer=layer, role=role,
                         kind="episode" if key != "demo-preference" else "preference",
                         subject="companion" if layer == "canon" else "user", qualifiers=qualifiers, request_id=key)
    result = service.recall(s, "你还记得观测站和我们昨天聊的事吗", token_budget=2400)
    print("以下角色和经历均为虚构示例。组件返回记忆，尚未调用聊天模型生成角色回复。\n")
    print("角色身份：" + service.identity(s)["profile"]["self_description"])
    for hit in result["hits"]:
        print(f"\n[{hit['knowledge_layer']} / {hit['world_id']}] {hit['text']}")
    print(f"\n召回 {len(result['hits'])} 条，来源和时间已保留。")
    print("\n组件状态：" + dumps(service.health(s)))


def console(service):
    s = Scope("local-user", "my-companion", ("real", "canon:my-story", "branch:my-story"))
    print("桌宠记忆组件 0.1.0\n这是独立记忆工作台。输入 /帮助 查看命令。")
    print("内容只保存在当前组件目录；角色的原作资料需要你之后提供。")
    while True:
        try:
            line = input("\n记忆> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        try:
            if line in {"/退出", "quit", "exit"}:
                break
            elif line == "/帮助":
                print("/身份 名称|作品名  设置她的身份和来源认知\n/记住 内容\n/原作 内容\n/剧情 内容\n/查 问题\n/列表\n/纠正 ID|新内容\n/更新 ID|新内容\n/忘记 ID\n/整理\n/状态\n/退出")
            elif line.startswith("/身份 "):
                name, origin = line[4:].split("|", 1)
                result = service.set_identity(s, {"name": name.strip(), "origin": origin.strip(), "knows_origin": True,
                    "self_description": f"我是{name.strip()}，来自{origin.strip()}。我了解现实，也记得故事里的过往和与你的新经历。",
                    "visible_world_ids": list(s.visible_world_ids)}, expected_revision=service.identity(s)["revision"])
                print(dumps(result))
            elif any(line.startswith(prefix) for prefix in ("/记住 ", "/原作 ", "/剧情 ")):
                prefix, text = line.split(" ", 1)
                world, layer, role = {"/记住": ("real", "shared_experience", "user"),
                    "/原作": ("canon:my-story", "canon", "document"),
                    "/剧情": ("branch:my-story", "story_branch", "user")}[prefix]
                print(dumps(service.remember(s, text, world_id=world, knowledge_layer=layer, role=role, request_id=uuid.uuid4().hex)))
            elif line.startswith("/查 "):
                result = service.recall(s, line[3:], token_budget=2400)
                if not result["hits"]:
                    print("没有找到相关记忆。")
                for hit in result["hits"]:
                    print(f"[{hit['knowledge_layer']}] {hit['text']}  ID={hit['memory_id']}")
                if result["degraded_channels"]:
                    print("部分检索通道暂不可用，已使用本地检索。")
            elif line == "/列表":
                for item in service.inspect(s)["items"]:
                    print(f"{item['memory_id']} v{item['revision']} [{item['knowledge_layer']}] {item['text']}")
            elif line.startswith(("/纠正 ", "/更新 ")):
                mid, text = line[4:].split("|", 1)
                items = service.inspect(s, memory_id=mid.strip())["items"]
                require(bool(items), "not_found", "未找到该记忆")
                print(dumps(service.correct(s, mid.strip(), text.strip(), expected_revision=items[0]["revision"],
                                           mode="retract" if line.startswith("/纠正") else "change")))
            elif line.startswith("/忘记 "):
                mid = line[4:].strip()
                items = service.inspect(s, memory_id=mid)["items"]
                require(bool(items), "not_found", "未找到该记忆")
                print(dumps(service.forget(s, mid, expected_revision=items[0]["revision"])))
            elif line == "/整理":
                print(dumps(service.process_pending()))
            elif line == "/状态":
                print(dumps(service.health(s)))
            elif line:
                print("这是记忆工作台，使用 /记住 保存或 /查 检索。输入 /帮助 查看命令。")
        except MemoryError as exc:
            print(f"未完成：{exc} ({exc.code})")
        except (ValueError, TypeError):
            print("命令格式有误，输入 /帮助 查看示例。")


def main():
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="独立桌宠记忆组件")
    parser.add_argument("command", choices=["console", "serve", "demo", "maintain"], nargs="?", default="console")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--providers", action="store_true", help="使用显式配置的 PET_MEMORY_* 模型接口")
    args = parser.parse_args()
    default_name = "demo.sqlite" if args.command == "demo" else "memory.sqlite"
    path = args.db or os.getenv("PET_MEMORY_DB") or Path(__file__).resolve().parent.parent / "data" / default_name
    try:
        options = from_environment() if args.providers else {}
        with MemoryService(path, **options) as service:
            if args.command == "serve":
                serve(service)
            elif args.command == "demo":
                demo(service)
            elif args.command == "maintain":
                print(dumps(service.process_pending(retry_failed=True)))
            else:
                console(service)
    except MemoryError as exc:
        print(dumps({"error": {"code": exc.code, "message": str(exc)}}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
