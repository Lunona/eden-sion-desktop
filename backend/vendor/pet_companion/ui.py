from __future__ import annotations

import math
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from pet_memory.types import MemoryError

BG, PANEL, INK, MUTED, GREEN = "#f4f3ef", "#ffffff", "#243c3a", "#71817b", "#396a58"
PHASES = {"idle": "空闲", "thinking": "正在思考", "waiting_for_provider": "等待上一项模型请求结束",
          "ready": "回复已准备", "presenting": "正在表达", "paused": "已暂停"}
MOODS = {"calm": "平静", "joyful": "愉快", "concerned": "关切", "tired": "疲倦", "focused": "专注"}
LAYERS = {"canon": "原作过往", "shared_experience": "共同经历", "realworld": "现实资料", "story_branch": "补充剧情"}
EXPRESSIONS = {"neutral": "自然", "smile": "微笑", "thoughtful": "思考", "concerned": "关切", "sleepy": "困倦"}
MOTIONS = {"idle": "站定", "nod": "点头", "head_tilt": "侧头", "wave": "挥手", "all": "全部动作"}


class Workbench:
    def __init__(self, runtime):
        self.runtime = runtime
        self.root = tk.Tk()
        self.root.title("桌宠联动工作台")
        self.root.geometry("1120x780")
        self.root.minsize(1000, 700)
        self.root.configure(bg=BG)
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9), background="#e8ece5", foreground=INK)
        style.map("TNotebook.Tab", background=[("selected", PANEL)])
        style.configure("Treeview", rowheight=33, font=("Microsoft YaHei UI", 10), background=PANEL, fieldbackground=PANEL)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        self.cursor = 0
        self.closed = False
        self.expression = "neutral"
        self.motion = "idle"
        self.motion_frame = 0
        self.mouth_level = 0.0
        self.memory_items = {}
        self._build()
        self._load_history()
        self.refresh_memories()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self._poll)

    def label(self, parent, text, *, size=10, color=INK, bold=False, **kwargs):
        return tk.Label(parent, text=text, fg=color, bg=parent.cget("bg"),
                        font=("Microsoft YaHei UI", size, "bold" if bold else "normal"), **kwargs)

    def button(self, parent, text, command, *, primary=False):
        return tk.Button(parent, text=text, command=command, bg=GREEN if primary else "#edf0e9",
            fg="white" if primary else INK, activebackground="#315e4c" if primary else "#dde6db",
            activeforeground="white" if primary else INK, relief="flat", bd=0, padx=16, pady=9, cursor="hand2")

    def _build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=26, pady=(22, 16))
        self.label(header, "桌宠联动工作台", size=21, bold=True).pack(side="left")
        mode = "离线联动演示" if self.runtime.model.mode == "offline_demo" else "已配置聊天模型"
        self.label(header, mode, color=GREEN).pack(side="right")
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=26, pady=(0, 14))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        side = tk.Frame(body, bg=PANEL, width=265, padx=20, pady=20)
        side.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        side.grid_propagate(False)
        self.name_label = self.label(side, self.runtime.profile.name, size=17, bold=True)
        self.name_label.pack(anchor="w")
        self.origin_label = self.label(side, self.runtime.profile.origin, size=10, color=MUTED, wraplength=225, justify="left")
        self.origin_label.pack(anchor="w", pady=(4, 14))
        self.canvas = tk.Canvas(side, width=225, height=185, bg="#f0f4ed", highlightthickness=0)
        self.canvas.pack(fill="x")
        self.label(side, "表情与动作示意", size=9, color=MUTED).pack(pady=(7, 18))
        self.phase_label = self.label(side, "空闲", size=13, bold=True)
        self.phase_label.pack(anchor="w")
        self.mood_label = self.label(side, "心情：平静", color=MUTED)
        self.mood_label.pack(anchor="w", pady=(10, 5))
        self.familiarity_label = self.label(side, "相处：初识", color=MUTED)
        self.familiarity_label.pack(anchor="w")
        self.face_label = self.label(side, "表现：自然", color=MUTED)
        self.face_label.pack(anchor="w", pady=(5, 12))
        self.label(side, "精力", color=MUTED, size=9).pack(anchor="w")
        self.energy = ttk.Progressbar(side, maximum=1.0)
        self.energy.pack(fill="x", pady=(5, 18))
        self.label(side, "原作、现实与共同经历\n由同一个她理解和记住。", size=10, color=MUTED, justify="left", wraplength=225).pack(anchor="w")
        self.notebook = ttk.Notebook(body)
        self.notebook.grid(row=0, column=1, sticky="nsew")
        chat = tk.Frame(self.notebook, bg=PANEL, padx=18, pady=18)
        memory = tk.Frame(self.notebook, bg=PANEL, padx=18, pady=18)
        events = tk.Frame(self.notebook, bg=PANEL, padx=18, pady=18)
        profile = tk.Frame(self.notebook, bg=PANEL, padx=18, pady=18)
        for frame, title in ((chat, "对话"), (memory, "记忆"), (events, "动作记录"), (profile, "角色设定")):
            self.notebook.add(frame, text=title)
        chat.grid_columnconfigure(0, weight=1)
        chat.grid_rowconfigure(0, weight=1)
        self.chat = ScrolledText(chat, wrap="word", height=10, width=1, relief="flat", bg=PANEL, fg=INK, padx=5, pady=8, spacing3=8, state="disabled")
        self.chat.tag_configure("user", foreground="#526e66", font=("Microsoft YaHei UI", 10, "bold"))
        self.chat.tag_configure("character", foreground=GREEN, font=("Microsoft YaHei UI", 10, "bold"))
        self.chat.tag_configure("note", foreground=MUTED, font=("Microsoft YaHei UI", 9))
        self.chat.grid(row=0, column=0, sticky="nsew")
        quick = tk.Frame(chat, bg=PANEL)
        quick.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        for text, prompt in (("身份认知", "你知道自己来自哪里吗"), ("原作与昨天", "你还记得观测站和我们昨天聊的事吗"), ("心情变化", "我今天有点累")):
            self.button(quick, text, lambda p=prompt: self.send(p)).pack(side="left", padx=(0, 7))
        self.input = tk.Text(chat, height=3, wrap="word", relief="flat", bg="#f1f4ee", fg=INK, padx=12, pady=9)
        self.input.grid(row=2, column=0, sticky="ew")
        self.input.bind("<Return>", self._enter)
        controls = tk.Frame(chat, bg=PANEL)
        controls.grid(row=3, column=0, sticky="ew", pady=(9, 0))
        self.pause_button = self.button(controls, "暂停", self.pause)
        self.pause_button.pack(side="left")
        self.button(controls, "打断当前回复", self.interrupt).pack(side="left", padx=8)
        self.send_button = self.button(controls, "发送", self.send, primary=True)
        self.send_button.pack(side="right")
        self.label(memory, "查看她记住了什么，也可以纠正或清除具体内容。", color=MUTED).pack(anchor="w", pady=(0, 12))
        self.tree = ttk.Treeview(memory, columns=("source", "text"), show="headings", selectmode="browse")
        self.tree.heading("source", text="来源")
        self.tree.heading("text", text="记忆内容")
        self.tree.column("source", width=92, stretch=False)
        self.tree.column("text", width=500)
        self.tree.pack(fill="both", expand=True)
        row = tk.Frame(memory, bg=PANEL)
        row.pack(fill="x", pady=10)
        for text, command in (("刷新", self.refresh_memories), ("查看依据", self.inspect_memory),
                              ("纠正内容", self.correct_memory), ("忘记所选", self.forget_memory)):
            self.button(row, text, command).pack(side="left", padx=(0, 7))
        self.label(memory, "明确记住一件事", color=MUTED).pack(anchor="w")
        self.memory_input = tk.Entry(memory, bg="#f1f4ee", fg=INK, relief="flat")
        self.memory_input.pack(fill="x", ipady=10, pady=8)
        row = tk.Frame(memory, bg=PANEL)
        row.pack(fill="x")
        self.layer = ttk.Combobox(row, values=["共同经历", "原作过往", "补充剧情"], state="readonly", width=12)
        self.layer.current(0)
        self.layer.pack(side="left")
        self.button(row, "保存记忆", self.add_memory, primary=True).pack(side="right")
        self.events = ScrolledText(events, wrap="word", relief="flat", fg=INK, bg=PANEL, state="disabled")
        self.events.pack(fill="both", expand=True)
        self.label(profile, "固定设定与短期心情分别保存。", color=MUTED).pack(anchor="w", pady=(0, 16))
        self.profile_fields = {}
        for key, title in (("name", "她的名字"), ("origin", "作品来源"), ("speaking_style", "说话方式，用逗号分隔"),
                           ("traits", "稳定性格，用逗号分隔"), ("self_description", "她怎样认识自己")):
            self.label(profile, title).pack(anchor="w", pady=(8, 5))
            widget = tk.Entry(profile, bg="#f1f4ee", fg=INK, relief="flat")
            value = getattr(self.runtime.profile, key)
            widget.insert(0, "，".join(value) if isinstance(value, tuple) else value)
            widget.pack(fill="x", ipady=9)
            self.profile_fields[key] = widget
        self.button(profile, "保存角色设定", self.save_profile, primary=True).pack(anchor="e", pady=20)
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(side="bottom", before=body, fill="x", padx=26, pady=(0, 14))
        notice = ("使用聊天模型时，当前消息与相关记忆会发送给所配服务。动作图为示意。" if self.runtime.model.mode == "configured_model"
                  else "离线组件工作台 · 图中为动作示意，尚未连接语音或桌宠。")
        self.notice = self.label(footer, notice, size=9, color=MUTED)
        self.notice.pack(anchor="w")
        self._draw()

    def _append_chat(self, label, text, tag="note"):
        self.chat.configure(state="normal")
        self.chat.insert("end", label + "\n", tag)
        self.chat.insert("end", text + "\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _load_history(self):
        history = self.runtime.history()
        if not history:
            self._append_chat("开始试一试", "可以问她来自哪里，或者聊聊示例里的观测站。")
        for row in history:
            self._append_chat("你", row["text"], "user")
            if row["reply"]:
                self._append_chat(self.runtime.profile.name, row["reply"], "character")
        # Historical events are not replayed as new replies or new actions.
        self.cursor = self.runtime.status()["event_cursor"]

    def _enter(self, event):
        if event.state & 0x1:
            return None
        self.send()
        return "break"

    def send(self, text=None):
        text = text if isinstance(text, str) else self.input.get("1.0", "end").strip()
        if not text:
            return
        try:
            self.runtime.send(text)
            self._append_chat("你", text, "user")
            self.input.delete("1.0", "end")
        except MemoryError as exc:
            self.notice.configure(text=str(exc))

    def interrupt(self):
        self.runtime.interrupt()
        self.notice.configure(text="当前回复与动作已停止。")

    def pause(self):
        self.runtime.pause(not self.runtime.paused)
        self.pause_button.configure(text="恢复" if self.runtime.paused else "暂停")

    def _event_line(self, text):
        self.events.configure(state="normal")
        self.events.insert("end", text + "\n\n")
        if int(self.events.index("end-1c").split(".")[0]) > 500:
            self.events.delete("1.0", "20.0")
        self.events.configure(state="disabled")
        self.events.see("end")

    def _handle(self, event):
        kind, p, tid = event["type"], event["payload"], event["turn_id"]
        if kind == "reply.ready":
            if self.runtime.can_present(tid, p["generation"]):
                self._append_chat(self.runtime.profile.name, p["plan"]["text"], "character")
                ack = self.runtime.acknowledge(tid, p["generation"], len(p["plan"]["text"]), completed=True)
                if ack["status"] == "ignored_stale":
                    self.notice.configure(text="记忆在显示时更新了，请重新发送这条消息。")
            else:
                self.runtime.interrupt("stale_context")
                self.notice.configure(text="记忆刚刚更新，请重新发送这条消息。")
        elif kind == "expression.set":
            self.expression = p["name"]
            self.face_label.configure(text="表现：" + EXPRESSIONS.get(self.expression, self.expression))
        elif kind == "motion.play":
            self.motion, self.motion_frame = p["name"], 0
            self._event_line("动作：" + MOTIONS.get(self.motion, self.motion))
        elif kind == "motion.stop":
            self.motion = "idle"
        elif kind == "mouth.level":
            self.mouth_level = p["level"]
        elif kind == "memory.recalled":
            sources = "、".join(LAYERS.get(x, x) for x in p["sources"])
            self._event_line(f"找到 {p['count']} 条相关记忆" + ("：" + sources if sources else ""))
        elif kind == "turn.interrupted":
            self._event_line("上一轮已打断，后续旧回复不会再显示。")
        elif kind == "turn.failed":
            self.notice.configure(text="这轮未完成，请检查模型设置或重新发送。")
        elif kind in {"memory.erased", "memory.corrected", "memory.added"}:
            self.refresh_memories()
            if kind == "memory.erased":
                self.chat.configure(state="normal")
                self.chat.delete("1.0", "end")
                self.chat.configure(state="disabled")
                self._load_history()

    def _poll(self):
        if self.closed:
            return
        try:
            batch = self.runtime.poll(self.cursor)
            self.cursor = batch["next_cursor"]
            for event in batch["events"]:
                self._handle(event)
            status = self.runtime.status()
            self.phase_label.configure(text=PHASES.get(status["phase"], status["phase"]))
            self.mood_label.configure(text="心情：" + MOODS.get(status["state"]["mood"], "平静"))
            self.familiarity_label.configure(text="相处：" + status["state"]["familiarity"])
            self.energy["value"] = status["state"]["energy"]
            self.motion_frame += 1
            self._draw()
        except MemoryError as exc:
            self.notice.configure(text=str(exc))
        self.root.after(80, self._poll)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        shift = 4 * math.sin(self.motion_frame * 0.6) if self.motion == "nod" else 0
        lean = 5 if self.motion == "head_tilt" else 0
        c.create_oval(48 + lean, 28 + shift, 177 + lean, 157 + shift, fill="#dbe8d6", outline="")
        c.create_arc(45 + lean, 14 + shift, 181 + lean, 126 + shift, start=12, extent=156, style="arc", width=10, outline="#6e8a76")
        if self.expression == "smile":
            for x in (88, 137):
                c.create_arc(x - 9 + lean, 75 + shift, x + 9 + lean, 94 + shift, start=20, extent=140, style="arc", outline=INK, width=2)
        elif self.expression == "sleepy":
            for x in (88, 137):
                c.create_line(x - 8 + lean, 86 + shift, x + 8 + lean, 86 + shift, fill=INK, width=2)
        else:
            for x in (88, 137):
                c.create_oval(x - 4 + lean, 78 + shift, x + 4 + lean, 91 + shift, fill=INK, outline="")
        if self.expression == "concerned":
            c.create_line(79 + lean, 73 + shift, 97 + lean, 69 + shift, fill=INK, width=2)
            c.create_line(128 + lean, 69 + shift, 146 + lean, 73 + shift, fill=INK, width=2)
        if self.mouth_level > 0:
            c.create_oval(106 + lean, 113 + shift, 119 + lean, 116 + shift + self.mouth_level * 10, fill="#6e8a76", outline="")
        else:
            c.create_line(104 + lean, 119 + shift, 121 + lean, 119 + shift, fill=INK, width=2)
        if self.motion == "wave":
            c.create_line(177, 132, 192, 92 + 8 * math.sin(self.motion_frame), fill="#6e8a76", width=8, capstyle="round")

    def refresh_memories(self):
        items = self.runtime.memory.inspect(self.runtime.scope(), limit=200)["items"]
        self.tree.delete(*self.tree.get_children())
        self.memory_items = {}
        for item in items:
            key = item["memory_id"]
            self.memory_items[key] = item
            self.tree.insert("", "end", iid=key, values=(LAYERS.get(item["knowledge_layer"], item["knowledge_layer"]), item["text"]))

    def selected_memory(self):
        selected = self.tree.selection()
        return self.memory_items.get(selected[0]) if selected else None

    def add_memory(self):
        text = self.memory_input.get().strip()
        if not text:
            return
        label = self.layer.get()
        world, layer = "real", "shared_experience"
        if label != "共同经历":
            prefix, layer = ("canon:", "canon") if label == "原作过往" else ("branch:", "story_branch")
            world = next((w for w in self.runtime.profile.world_ids if w.startswith(prefix)), None)
            if not world:
                self.notice.configure(text="当前角色尚未配置这类剧情来源。")
                return
        try:
            self.runtime.remember(text, world_id=world, knowledge_layer=layer)
            self.memory_input.delete(0, "end")
            self.refresh_memories()
            self.notice.configure(text="这条记忆已经保存。")
        except MemoryError as exc:
            self.notice.configure(text=str(exc))

    def inspect_memory(self):
        item = self.selected_memory()
        if item:
            evidence = "\n\n".join(e["quote"] for e in item["evidence"])
            messagebox.showinfo("记忆依据", item["text"] + "\n\n来源：" + LAYERS.get(item["knowledge_layer"], "") + "\n\n原文依据：\n" + evidence, parent=self.root)

    def correct_memory(self):
        item = self.selected_memory()
        if item:
            text = simpledialog.askstring("纠正内容", "正确内容", initialvalue=item["text"], parent=self.root)
            if text:
                try:
                    self.runtime.correct_memory(item["memory_id"], text, item["revision"], mode="retract")
                    self.refresh_memories()
                except MemoryError as exc:
                    self.notice.configure(text=str(exc))

    def forget_memory(self):
        item = self.selected_memory()
        if item:
            try:
                self.runtime.forget_memory(item["memory_id"], item["revision"])
                self.refresh_memories()
                self.notice.configure(text="所选记忆和依赖它的记录已清除。")
            except MemoryError as exc:
                self.notice.configure(text=str(exc))

    def save_profile(self):
        profile = self.runtime.profile.as_dict()
        for key, widget in self.profile_fields.items():
            value = widget.get().strip()
            profile[key] = [v.strip() for v in value.replace(",", "，").split("，") if v.strip()] if key in {"traits", "speaking_style"} else value
        try:
            self.runtime.set_profile(profile, expected_revision=self.runtime.profile_revision)
            self.name_label.configure(text=self.runtime.profile.name)
            self.origin_label.configure(text=self.runtime.profile.origin)
            self.notice.configure(text="角色设定已保存，记忆中的身份已同步。")
        except MemoryError as exc:
            self.notice.configure(text=str(exc))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.runtime.interrupt("window_closed")
        self.root.destroy()
