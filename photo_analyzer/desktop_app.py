from __future__ import annotations

import random
import threading
from pathlib import Path
from tkinter import Canvas, StringVar, Tk, ttk, filedialog, messagebox

from PIL import Image, ImageTk

from .cli import DEFAULT_SAMPLE_COUNT, DEFAULT_SAMPLE_SEED, collect_targets
from .core import AnalysisError, AnalysisResult, analyze_image

MAX_SAMPLE_COUNT = 100
THUMBNAIL_SIZE = (260, 200)


def build_card_tags(result: AnalysisResult) -> list[str]:
    return result.tags or ["无描述标签"]


def clamp_sample_count(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_SAMPLE_COUNT
    return min(MAX_SAMPLE_COUNT, max(1, value))


class DesktopGalleryApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Photo Analyzer 本地标签画廊")
        self.root.geometry("1380x920")

        self.directory_var = StringVar()
        self.count_var = StringVar(value=str(DEFAULT_SAMPLE_COUNT))
        self.status_var = StringVar(value="选择本地目录后开始抽样分析。")

        self._all_targets: list[Path] = []
        self._image_refs: list[ImageTk.PhotoImage] = []
        self._running = False

        self._build_ui()

    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        controls = ttk.Frame(root, padding=16)
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=0)
        controls.columnconfigure(3, weight=0)

        ttk.Label(controls, text="目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(
            controls,
            textvariable=self.directory_var,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(controls, text="选择本地目录", command=self.select_directory).grid(
            row=0, column=2, sticky="ew"
        )

        ttk.Label(controls, text="测试照片数").grid(row=1, column=0, sticky="w", pady=(12, 0))
        ttk.Spinbox(
            controls,
            from_=1,
            to=MAX_SAMPLE_COUNT,
            textvariable=self.count_var,
            width=8,
        ).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(12, 0))

        self.run_button = ttk.Button(
            controls,
            text="开始抽样分析",
            command=self.run_analysis,
        )
        self.run_button.grid(row=1, column=2, sticky="e", padx=(12, 0), pady=(12, 0))

        ttk.Label(
            controls,
            textvariable=self.status_var,
            wraplength=1200,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        canvas_frame = ttk.Frame(root, padding=(16, 0, 16, 16))
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self._scroll_canvas = Canvas(
            canvas_frame,
            highlightthickness=0,
            background="#f5f1ea",
        )
        self._scroll_canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            canvas_frame,
            orient="vertical",
            command=self._scroll_canvas.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)

        self.cards_frame = ttk.Frame(self._scroll_canvas, padding=4)
        self.cards_frame.bind(
            "<Configure>",
            lambda _event: self._scroll_canvas.configure(
                scrollregion=self._scroll_canvas.bbox("all")
            ),
        )
        self._canvas_window = self._scroll_canvas.create_window(
            (0, 0), window=self.cards_frame, anchor="nw"
        )
        self._scroll_canvas.bind(
            "<Configure>",
            lambda event: self._scroll_canvas.itemconfigure(self._canvas_window, width=event.width),
        )

    def select_directory(self) -> None:
        selected = filedialog.askdirectory(title="选择图片目录")
        if not selected:
            return

        try:
            targets = collect_targets(selected)
        except AnalysisError as exc:
            messagebox.showerror("目录不可用", str(exc), parent=self.root)
            return

        self._all_targets = targets
        self.directory_var.set(selected)
        self.status_var.set(
            f"已记录目录，共 {len(targets)} 张图片。点击“开始抽样分析”后只会按右侧数量读取并分析抽中的图片。"
        )

    def run_analysis(self) -> None:
        if self._running:
            return
        if not self._all_targets:
            messagebox.showinfo("尚未选择目录", "请先选择本地图片目录。", parent=self.root)
            return

        count = min(clamp_sample_count(self.count_var.get()), len(self._all_targets))
        self.count_var.set(str(count))

        self._running = True
        self.run_button.state(["disabled"])
        self.status_var.set(f"正在本地分析 {count} 张图片，不会启动任何 web service。")

        worker = threading.Thread(
            target=self._analyze_targets,
            args=(count,),
            daemon=True,
        )
        worker.start()

    def _analyze_targets(self, count: int) -> None:
        chosen = (
            sorted(self._all_targets)
            if len(self._all_targets) <= count
            else sorted(random.Random(DEFAULT_SAMPLE_SEED).sample(self._all_targets, count))
        )

        cards: list[tuple[Path, AnalysisResult]] = []
        failures = 0
        for target in chosen:
            try:
                result = analyze_image(str(target))
            except AnalysisError:
                failures += 1
                continue
            cards.append((target, result))

        self.root.after(0, lambda: self._render_results(cards, failures, count))

    def _clear_cards(self) -> None:
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        self._image_refs.clear()

    def _render_results(
        self,
        cards: list[tuple[Path, AnalysisResult]],
        failures: int,
        requested_count: int,
    ) -> None:
        self._clear_cards()
        columns = 4

        for index, (path, result) in enumerate(cards):
            card = ttk.Frame(self.cards_frame, padding=10, relief="ridge")
            row = index // columns
            column = index % columns
            card.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)

            preview = self._build_thumbnail(path)
            if preview is not None:
                image_label = ttk.Label(card, image=preview)
                image_label.image = preview
                image_label.grid(row=0, column=0, sticky="ew")
                self._image_refs.append(preview)

            ttk.Label(
                card,
                text=path.name,
                wraplength=240,
                justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(8, 6))

            caption_text = (result.caption or "").strip() or "—"
            ttk.Label(
                card,
                text=caption_text,
                wraplength=240,
                justify="left",
            ).grid(row=2, column=0, sticky="w", pady=(0, 6))

            ttk.Label(
                card,
                text="  ".join(build_card_tags(result)),
                wraplength=240,
                justify="left",
            ).grid(row=3, column=0, sticky="w")

        self.run_button.state(["!disabled"])
        self._running = False
        self.status_var.set(
            f"已完成：请求 {requested_count} 张，成功分析 {len(cards)} 张，失败 {failures} 张。"
        )

    def _build_thumbnail(self, path: Path) -> ImageTk.PhotoImage | None:
        try:
            with Image.open(path) as image:
                preview = image.convert("RGB")
                preview.thumbnail(THUMBNAIL_SIZE)
        except OSError:
            return None
        return ImageTk.PhotoImage(preview)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def main() -> int:
    try:
        app = DesktopGalleryApp()
    except Exception as exc:
        print(f"无法启动本地桌面应用：{exc}")
        return 1
    return app.run()
