import threading
import time
from pathlib import Path
from typing import Optional

import react_ipywidgets as react
from react_ipywidgets import component
from react_ipywidgets import ipywidgets as w
from react_ipywidgets import render_fixed

import solara as sol
from solara.datatypes import FileContentResult
from solara.hooks.misc import use_download, use_fetch, use_json, use_thread


def test_hook_thread():
    done = False

    @component
    def ThreadTest():
        nonlocal done
        a, _ = react.use_state("a")
        b, _ = react.use_state("b")
        counter, set_counter = react.use_state(0)
        other, set_other = react.use_state(0)
        c, _ = react.use_state("c")
        if counter % 2 == 0:
            set_other(counter)

        def work(cancelled):
            for i in range(256):
                set_counter(i)
                time.sleep(0.001)

        use_thread(work, [])
        return w.Label(value=f"{a} {b} {c} {counter}")

    label, rc = render_fixed(ThreadTest(), handle_error=False)
    expected = "a b c 255"
    for i in range(200):  # max 2 second
        time.sleep(0.01)
        if label.value == expected:
            break
    assert label.value == expected


def test_use_thread_keep_previous():
    def set_x(x):
        pass

    @component
    def Test():
        nonlocal set_x
        x, set_x = react.use_state(2)

        def work():
            time.sleep(0.1)
            return x**2

        result: sol.Result[int] = use_thread(work, dependencies=[x])
        return w.Label(value=f"{result.value}")

    label, rc = render_fixed(Test(), handle_error=False)
    expected_2 = "4"
    for i in range(200):  # max 2 second
        time.sleep(0.01)
        if label.value == expected_2:
            break
    assert label.value == expected_2

    expected_3 = "9"
    set_x(3)
    for i in range(200):  # max 2 second
        time.sleep(0.01)
        if label.value == expected_3:
            break
        else:
            assert label.value == expected_2
    assert label.value == expected_3


def test_hook_iterator():
    event = threading.Event()
    result = None

    @react.component
    def Test():
        nonlocal result

        def work():
            yield 1
            event.wait()
            yield 2

        result = use_thread(work)
        return w.Label(value="test")

    label, rc = react.render_fixed(Test())
    assert result is not None
    assert isinstance(result, sol.Result)
    time.sleep(0.05)
    assert result.value == 1
    event.set()
    time.sleep(0.01)
    assert isinstance(result, sol.Result)
    assert result.value == 2


def test_use_thread_intrusive_cancel():
    result = None
    last_value = 0
    seconds = 4

    @react.component
    def Test():
        nonlocal result
        nonlocal last_value

        def work():
            nonlocal last_value
            for i in range(100):
                last_value = i
                # if not cancelled, might take 4 seconds
                time.sleep(seconds / 100)
            return 2**42

        result = use_thread(work, dependencies=[])
        return w.Label(value="test")

    react.render_fixed(Test())
    assert result is not None
    assert isinstance(result, sol.Result)
    result.cancel()
    while result.state == sol.ResultState.RUNNING:
        time.sleep(0.1)
    assert result.state == sol.ResultState.CANCELLED
    assert last_value != 99

    # also test retry
    seconds = 0.1
    result.retry()
    while result.state == sol.ResultState.CANCELLED:
        time.sleep(0.1)
    while result.state == sol.ResultState.RUNNING:
        time.sleep(0.1)
    assert last_value == 99


def test_hook_download(tmpdir):
    url = "https://raw.githubusercontent.com/widgetti/react-ipywidgets/master/.gitignore"
    content_length = 865

    path = tmpdir / "file.txt"

    @component
    def DownloadFile(url=url, expected_size=None):
        result = use_download(path, url, expected_size=expected_size)
        return w.Label(value=f"{result.progress} {result.state} {result.error}")

    label, rc = render_fixed(DownloadFile())
    assert label.value == "0 ResultState.RUNNING None"
    expected = "1.0 ResultState.FINISHED None"
    for i in range(200):  # max 2 second
        time.sleep(0.01)
        if label.value == expected:
            break
    assert label.value == expected

    # if given, content_length, we should render with done immediately
    label, rc = render_fixed(DownloadFile(expected_size=content_length))
    time.sleep(0.05)
    assert label.value == expected

    label, rc = render_fixed(DownloadFile(url=url + ".404"))
    expected = "0 ResultState.ERROR HTTP Error 404: Not Found"
    for i in range(50):  # max 0.5 second
        time.sleep(0.01)
        if label.value == expected:
            break
    assert label.value == expected


def test_hook_use_fetch():
    url = "https://raw.githubusercontent.com/widgetti/react-ipywidgets/master/.gitignore"
    content_length = 865

    result = None

    @component
    def FetchFile(url=url, expected_size=None):
        nonlocal result
        result = use_fetch(url)
        data = result.value
        return w.Label(value=f"{len(data) if data else '-'}")

    label, rc = render_fixed(FetchFile())
    assert label.value == "-"
    expected = f"{content_length}"
    for i in range(200):  # max 2 second
        time.sleep(0.01)
        if label.value == expected:
            break
    assert label.value == expected


def test_hook_use_json():
    url = "https://jherr-pokemon.s3.us-west-1.amazonaws.com/index.json"
    pokemons = 799

    result = None

    @component
    def FetchJson(url=url, expected_size=None):
        nonlocal result
        result = use_json(url)
        data = result.value
        return w.Label(value=f"{len(data) if data else '-'}")

    label, rc = render_fixed(FetchJson())
    assert label.value == "-"
    expected = f"{pokemons}"
    for i in range(200):  # max 2 second
        time.sleep(0.01)
        if label.value == expected:
            break
    assert label.value == expected


def test_use_file_content(tmpdir: Path):
    path = tmpdir / "test.txt"
    path.write_text("Hi", "utf8")

    result: Optional[FileContentResult[bytes]] = None

    @react.component
    def Test(path):
        nonlocal result
        result = sol.use_file_content(path)
        if result.value is not None:
            assert result.value == b"Hi"
            assert result.exists
        else:
            assert isinstance(result.error, FileNotFoundError)
            assert not result.exists
        # pickle.dumps(result)
        return w.Button()

    react.render_fixed(Test(path))
    path_non_exist = tmpdir / "nonexist"
    react.render_fixed(Test(path_non_exist))
    path_non_exist.write_text("Hi", "utf8")
    assert result is not None
    result.retry()
    assert result.value == b"Hi"


def test_use_state_or_update():
    values = []
    set_value = None

    @react.component
    def Test(value):
        nonlocal set_value
        value, set_value = sol.use_state_or_update(value)
        values.append(value)
        return w.Button()

    container, rc = react.render(Test(3))
    assert set_value is not None
    assert values == [3]
    set_value(5)
    assert values == [3, 5]
    rc.render(Test(9))
    assert values == [3, 5, 9, 9]  # we render twice, since we call set_state in or_update
