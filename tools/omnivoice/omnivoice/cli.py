import functools
import sys
import typer
from pathlib import Path
from omnivoice import __version__
from omnivoice.project import Project, ProjectError
from omnivoice import dataset as ds
from omnivoice import slicer
from omnivoice import transcriber
from omnivoice import checker
from omnivoice.hints import NEED_UI

app = typer.Typer(help="omnivoice — обучение и упаковка голосов для OmniChat", no_args_is_help=True)

def _version(value: bool):
    if value:
        typer.echo(f"omnivoice {__version__}"); raise typer.Exit()

def _force_utf8() -> None:
    """Windows pipes default to cp1251, which mangles Cyrillic; force UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

def _friendly(fn):
    """Corrupt / missing project files surface as a red Russian message and exit 1, never a traceback."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ProjectError as e:
            typer.secho(str(e), fg="red"); raise typer.Exit(1)
    return wrapper

@app.callback()
def main(version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Показать версию")):
    _force_utf8()

def _load(project: Path) -> Project:
    """Load a project, handling ProjectError."""
    try:
        return Project.load(project)
    except ProjectError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)

@app.command()
@_friendly
def init(directory: Path, name: str = typer.Option(..., help="Имя голоса"),
         language: str = typer.Option("ru", help="Язык: ru или en"),
         base: str = typer.Option(None, help="Базовая модель: denis, dmitri, irina, ruslan, lessac")):
    """Создать проект голоса."""
    try:
        p = Project.create(directory, name=name, language=language, base=base)
    except ProjectError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.secho(f"Проект «{p.name}» создан в {p.root}", fg="green")

@app.command("import")
@_friendly
def import_cmd(source: Path, project: Path = typer.Option(Path("."), "--project", "-p")):
    """Импортировать готовый датасет (LJSpeech или пары .wav + .txt)."""
    try:
        r = ds.import_dataset(_load(project), source)
    except ProjectError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.secho(f"Добавлено фраз: {r.added}", fg="green")
    if r.skipped_existing:
        typer.echo(f"Пропущено (уже импортировано): {r.skipped_existing}")
    if r.missing_audio:
        typer.secho(f"Нет аудиофайла ({len(r.missing_audio)}): " + ", ".join(r.missing_audio[:10])
                    + (" …" if len(r.missing_audio) > 10 else ""), fg="yellow")
    if r.failed:
        typer.secho(f"Не удалось прочитать ({len(r.failed)}): " + ", ".join(r.failed[:10])
                    + (" …" if len(r.failed) > 10 else ""), fg="yellow")

@app.command("slice")
@_friendly
def slice_cmd(project: Path = typer.Option(Path("."), "--project", "-p"),
              isolate: bool = typer.Option(False, "--isolate", help="Отделить голос от музыки (demucs)")):
    """Нарезать сырое аудио из raw/ на фразы."""
    proj = _load(project)
    try:
        n = slicer.slice_project(proj, isolate=isolate)
    except RuntimeError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.secho(f"Новых фраз: {n}", fg="green")

@app.command("transcribe")
@_friendly
def transcribe_cmd(project: Path = typer.Option(Path("."), "--project", "-p"),
                   model: str = typer.Option(None, "--model", help="Модель Whisper (по умолчанию large-v3 на GPU, medium на CPU)")):
    """Распознать текст фраз (Whisper)."""
    proj = _load(project)
    try:
        n = transcriber.transcribe_project(proj, model=model)
    except RuntimeError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.secho(f"Распознано фраз: {n}", fg="green")

@app.command("check")
@_friendly
def check_cmd(project: Path = typer.Option(Path("."), "--project", "-p")):
    """Проверить качество датасета."""
    proj = _load(project)
    r = checker.check_project(proj)

    # Print summary
    typer.echo(f"Всего минут: {r.total_minutes}, фраз: {r.phrases}")

    # Print warnings
    for w in r.warnings:
        typer.secho(w, fg="yellow")

    # Print errors
    for e in r.errors:
        typer.secho(e, fg="red")

    # Print per-segment issues table
    if r.per_segment:
        typer.echo("\nПроблемы по фразам:")
        for seg_id, issues in sorted(r.per_segment.items()):
            typer.echo(f"  {seg_id}: {', '.join(issues)}")

    # Exit with code 1 if there are errors
    if r.errors:
        raise typer.Exit(1)

@app.command("pack")
@_friendly
def pack_cmd(project: Path = typer.Option(Path("."), "--project", "-p"),
             onnx: Path = typer.Option(None, "--onnx", help="Готовая .onnx модель (чужая или своя)"),
             config: Path = typer.Option(None, "--config", help=".onnx.json модели"),
             voice: str = typer.Option(None, "--voice", help="Голос espeak, например ru"),
             name: str = typer.Option(None, "--name", help="Имя голоса (обязательно с --onnx)"),
             language: str = typer.Option(None, "--language",
                                          help="Английское название языка для метаданных (по умолчанию из --voice)"),
             out_dir: Path = typer.Option(Path("."), "--out", help="Папка вывода для режима --onnx"),
             portrait: Path = typer.Option(None, "--portrait", help="Картинка для портрета")):
    """Собрать папку голоса для мода OmniChat."""
    from omnivoice import pack as packer
    if onnx is not None and not name:
        typer.secho("Укажи имя голоса через --name", fg="red"); raise typer.Exit(1)
    proj = _load(project) if onnx is None else None
    try:
        if onnx is not None:
            language = language or packer.iso_name_for_voice(voice or packer.config_voice(config))
            out = packer.pack_voice(onnx, config, out_dir, {"name": name}, language, voice_override=voice,
                                    portrait_bytes=portrait.read_bytes() if portrait else None)
        else:
            out = packer.pack_project(proj, portrait=portrait)
    except packer.PackError as e:
        for pr in e.problems:
            typer.secho(pr, fg="red")
        raise typer.Exit(1)
    except (RuntimeError, OSError) as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.secho(f"Голос собран: {out}", fg="green")

@app.command("verify")
@_friendly
def verify_cmd(folder: Path, text: str = typer.Option(None, "--text", help="Фраза для проверки")):
    """Проверить голос: загрузить в sherpa-onnx (в отдельном процессе) и озвучить фразу."""
    from omnivoice import verify as vf
    r = vf.verify_voice(folder, text)
    if not r.ok:
        typer.secho(r.message, fg="red"); raise typer.Exit(1)
    typer.secho(r.message, fg="green")
    typer.echo(f"Пример звучания: {r.sample}")

@app.command("install")
@_friendly
def install_cmd(folder: Path, target: Path = typer.Option(None, "--target", help="Папка models мода"),
                overwrite: bool = typer.Option(False, "--overwrite", help="Заменить существующий голос")):
    """Установить голос в папку models мода."""
    from omnivoice import install as inst
    from omnivoice.fsutil import TargetBusy
    if not Path(folder).is_dir():
        typer.secho(f"Папка голоса не найдена: {folder}", fg="red"); raise typer.Exit(1)
    if target is None:
        targets = inst.default_targets()
        if not targets:
            typer.secho("Не нашёл папку models мода — укажи её через --target", fg="red"); raise typer.Exit(1)
        if len(targets) == 1:
            target = targets[0]
        else:
            for i, t in enumerate(targets, 1):
                typer.echo(f"{i}. {t}")
            idx = typer.prompt("Куда установить? Номер", type=int)
            if not 1 <= idx <= len(targets):
                typer.secho("Нет такого номера", fg="red"); raise typer.Exit(1)
            target = targets[idx - 1]
    try:
        target.mkdir(parents=True, exist_ok=True)
        dest = inst.install_voice(folder, target, overwrite=overwrite)
    except (FileExistsError, TargetBusy, ValueError, OSError) as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.secho(f"Голос установлен: {dest}", fg="green")

@app.command("train")
@_friendly
def train_cmd(project: Path = typer.Option(Path("."), "--project", "-p"),
              epochs: int = typer.Option(1000, help="Сколько эпох дообучать поверх базовой модели"),
              no_resume: bool = typer.Option(False, "--no-resume", help="Не продолжать с последнего чекпойнта"),
              build: bool = typer.Option(False, "--build", help="Только собрать Docker-образ"),
              colab_: bool = typer.Option(False, "--colab", help="Подготовить zip для Colab")):
    """Дообучить голос (WSL или Docker с GPU) или подготовить zip для Colab."""
    from omnivoice import train as tr
    if build:  # the image doesn't depend on a project
        try:
            tr.build_image()
        except tr.TrainError as e:
            typer.secho(str(e), fg="red"); raise typer.Exit(1)
        return
    p = _load(project)
    try:
        if colab_:
            from omnivoice import colab
            z = colab.make_dataset_zip(p)
            typer.echo(f"Датасет: {z}")
            typer.echo(f"Открой ноутбук: {colab.NOTEBOOK_URL}"); return
        last = [-1]
        def progress(done, total):
            if total:
                pct = done * 100 // total // 5 * 5
                if pct > last[0]:
                    last[0] = pct; typer.echo(f"Скачиваю базовую модель: {pct}%")
        code = tr.train_project(p, epochs=epochs, resume=not no_resume, on_line=typer.echo, progress=progress)
    except (tr.TrainError, RuntimeError, OSError) as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    raise typer.Exit(code)

@app.command("export")
@_friendly
def export_cmd(project: Path = typer.Option(Path("."), "--project", "-p"),
               ckpt: Path = typer.Option(None, help="Чекпойнт (по умолчанию последний)")):
    """Экспортировать чекпойнт в ONNX, упаковать и проверить."""
    from omnivoice import train as tr, pack as pk, verify as vf
    p = _load(project)
    try:
        onnx_path = tr.export_project(p, ckpt)
        folder = pk.pack_project(p, onnx_path)
        r = vf.verify_voice(folder)
    except pk.PackError as e:
        for pr in e.problems:
            typer.secho(pr, fg="red")
        raise typer.Exit(1)
    except (tr.TrainError, RuntimeError, OSError, ValueError) as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    typer.secho(r.message, fg="green" if r.ok else "red")
    raise typer.Exit(0 if r.ok else 1)

@app.command("previews")
@_friendly
def previews_cmd(project: Path = typer.Option(Path("."), "--project", "-p")):
    """Показать чекпойнты и вытащить аудио-превью из логов обучения."""
    from omnivoice import previews as pv
    p = _load(project)
    cps = pv.list_checkpoints(p)
    if not cps:
        typer.echo("Чекпойнтов пока нет")
    for c in cps:
        extra = f"  {c.metric}={c.value:.4f}" if c.metric else ""
        typer.echo(f"эпоха {c.epoch}{extra}  {c.path}")
    try:
        found = pv.extract_previews(p)
    except RuntimeError as e:
        typer.secho(str(e), fg="red"); raise typer.Exit(1)
    n = sum(len(v) for v in found.values())
    typer.echo(f"Превью: {n} (шагов: {len(found)}) в {p.train_dir / 'previews'}")

@app.command("ui")
@_friendly
def ui_cmd(projects: Path = typer.Option(Path("."), "--projects", help="Папка с проектами голосов"),
           port: int = typer.Option(7860, "--port", help="Порт веб-интерфейса"),
           no_browser: bool = typer.Option(False, "--no-browser", help="Не открывать браузер")):
    """Открыть веб-интерфейс (нужен пакет omnivoice[ui])."""
    try:
        from omnivoice.ui.app import launch
    except ImportError:
        typer.secho(NEED_UI, fg="red"); raise typer.Exit(1)
    launch(projects, port=port, inbrowser=not no_browser)

def _item_line(it) -> str:
    opt = " (необязательно)" if it.optional else ""
    return f"{'✓' if it.ok else '✗'} {it.name}{opt} — {it.detail}"

def _print_checklist(items) -> bool:
    """Print ✓/✗ rows; returns True when every required item is OK."""
    for it in items:
        color = "green" if it.ok else ("yellow" if it.optional else "red")
        typer.secho(_item_line(it), fg=color)
    return all(it.ok for it in items if not it.optional)

class _Progress:
    """Download percent every 5 %, restarting when a new download begins."""
    def __init__(self):
        self.last = -1
    def __call__(self, done, total):
        if not total:
            return
        pct = min(100, done * 100 // total // 5 * 5)
        if pct < self.last:
            self.last = -1
        if pct > self.last:
            self.last = pct; typer.echo(f"Скачиваю: {pct}%")

def _setup_line(line: str) -> None:
    from omnivoice.wslenv import parse_step
    if step := parse_step(line):
        typer.secho(f"[{step[0]}/{step[1]}] {step[2]}", fg="cyan", bold=True)
    else:
        typer.echo(line)

SOURCE_LABELS = {"env": "переменная окружения OMNIVOICE_CACHE", "config": "настройка {config}",
                 "default": "по умолчанию"}

@app.command("data-dir")
def data_dir_cmd(path: str = typer.Argument(None, help=r"Новая папка, например G:\omnivoice: всё будет перенесено туда")):
    """Показать или сменить папку для зависимостей (среда WSL, базовые модели, ffmpeg). Проекты не трогаются."""
    from omnivoice import datadir, paths, wslenv
    code = 0  # typer.Exit is a RuntimeError too, so no raise typer.Exit inside the try
    try:
        if path is None:
            d, source, used = datadir.describe()
            typer.echo(f"Папка для зависимостей: {d}")
            typer.echo(f"Откуда: {SOURCE_LABELS[source].format(config=paths.config_path())}")
            typer.echo(f"Занято: {datadir.human_size(used)}")
            typer.echo("Сменить и перенести: omnivoice data-dir <новая папка>")
        else:
            datadir.move_data(path, typer.echo)
    except (datadir.DataDirError, wslenv.WslError, RuntimeError, OSError) as e:
        typer.secho(str(e) or type(e).__name__, fg="red")
        code = 1
    raise typer.Exit(code)

@app.command("setup")
def setup_cmd(check: bool = typer.Option(False, "--check", help="Только показать, чего не хватает"),
              data_dir: str = typer.Option(None, "--data-dir",
                                           help="Сначала сменить папку для зависимостей (как omnivoice data-dir)")):
    """Установить всё для подготовки и обучения: пакеты, ffmpeg, среду WSL."""
    from omnivoice import datadir, deps, train as tr, wslenv
    # typer.Exit is a RuntimeError too, so no raise typer.Exit inside the try
    errors = (datadir.DataDirError, deps.DepsError, wslenv.WslError, tr.TrainError, RuntimeError, OSError)
    code = 0
    try:
        if data_dir:
            datadir.move_data(data_dir, typer.echo)
            typer.echo("")
        ok = _print_checklist(deps.check_all())
        if check:
            if not ok:
                typer.secho("Чего-то не хватает — запусти «omnivoice setup» или нажми «Установить зависимости» "
                            "в интерфейсе", fg="red")
            code = 0 if ok else 1
        else:
            typer.echo("")
            reboot = deps.install_all(_setup_line, _Progress())
            if reboot:
                typer.secho(reboot, fg="yellow", bold=True)
                code = 2
            else:
                typer.echo("")
                if _print_checklist(deps.check_all()):
                    typer.secho("Всё установлено — можно обучать: omnivoice ui", fg="green")
                else:
                    typer.secho("Установка завершилась, но не всё готово — см. список выше", fg="red")
                    code = 1
    except errors as e:
        typer.secho(str(e) or type(e).__name__, fg="red")
        code = 1
    raise typer.Exit(code)
