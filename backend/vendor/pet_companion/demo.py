from __future__ import annotations

import time


def seed_demo(runtime):
    scope = runtime.scope()
    canon = next((w for w in scope.visible_world_ids if w.startswith("canon:")), None)
    if canon:
        runtime.memory.remember(scope, "故事第二章，我和朋友一起修好了山上的观测站。", kind="episode",
            world_id=canon, knowledge_layer="canon", role="document", subject="companion",
            qualifiers={"chapter": 2}, request_id="core-demo-canon")
    runtime.memory.remember(scope, "昨天我们聊过故事里的观测站，你说很喜欢那一段。", kind="episode",
                            request_id="core-demo-shared")


def run_demo(runtime):
    seed_demo(runtime)
    result = runtime.send("你还记得观测站和我们昨天聊的事吗", turn_id="demo-" + str(time.time_ns()))
    cursor = 0
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        runtime.tick()
        batch = runtime.poll(cursor)
        cursor = batch["next_cursor"]
        for event in batch["events"]:
            if event["type"] == "reply.ready" and event["turn_id"] == result["turn_id"]:
                p = event["payload"]
                runtime.acknowledge(event["turn_id"], p["generation"], len(p["plan"]["text"]), completed=True)
                print("离线联动演示，角色与经历均为虚构样例。\n")
                print(p["plan"]["text"])
                print("\n表情：", p["plan"]["expression"], "动作：", p["plan"]["motion"])
                print("状态：", runtime.status()["state"]["mood"])
                return result
            if event["type"] == "turn.failed":
                raise RuntimeError(event["payload"]["code"])
        time.sleep(0.01)
    raise TimeoutError("演示等待超时")
