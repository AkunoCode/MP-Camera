from PyQt6 import QtCore, QtWidgets, QtGui
import os

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebEngineView = None


def setup(chart_page, main_window):
    """Initialize the chart page webview and load the SoilSight web app."""
    try:
        # Try to find the promoted QWebEngineView by object name 'widget'
        webview = None
        if QWebEngineView is not None:
            webview = chart_page.findChild(QWebEngineView, "widget")
            if webview is None:
                children = chart_page.findChildren(QWebEngineView)
                webview = children[0] if children else None
        else:
            webview = chart_page.findChild(type(chart_page), "widget")

        # If not found and we can create one, do so
        if webview is None and QWebEngineView is not None:
            try:
                webview = QWebEngineView(chart_page)
                webview.setObjectName("widget")
                try:
                    webview.setGeometry(0, 0, chart_page.width() or 1100, chart_page.height() or 760)
                except Exception:
                    webview.setGeometry(0, 0, 1100, 760)
                webview.setParent(chart_page)
                webview.show()
            except Exception as e:
                print("chart_page: Failed to create QWebEngineView:", e)

        if webview is not None:
            # expose webview on the main window so other helpers can access it
            try:
                setattr(main_window, "chart_webview", webview)
            except Exception:
                pass

            try:
                from PyQt6.QtCore import QUrl

                url = QUrl("https://soilsight-one.vercel.app")
                if hasattr(webview, "setUrl"):
                    webview.setUrl(url)
                elif hasattr(webview, "load"):
                    webview.load(url)
                print("chart_page: webview instructed to load URL:", url.toString())
            except Exception as e:
                print("chart_page: Failed to load URL into webview:", e)

            # set default zoom and shortcuts on main_window
            try:
                if hasattr(webview, "setZoomFactor"):
                    webview.setZoomFactor(0.7)
                elif hasattr(webview, "page") and hasattr(webview.page(), "setZoomFactor"):
                    webview.page().setZoomFactor(0.7)
            except Exception:
                pass

            try:
                zoom_in_seq = QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.ZoomIn)
                zoom_out_seq = QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.ZoomOut)
                reset_seq = QtGui.QKeySequence("Ctrl+0")

                zoom_in_sc = QtWidgets.QShortcut(zoom_in_seq, main_window)
                zoom_in_sc.activated.connect(lambda: _change_zoom(webview, 0.1))

                zoom_out_sc = QtWidgets.QShortcut(zoom_out_seq, main_window)
                zoom_out_sc.activated.connect(lambda: _change_zoom(webview, -0.1))

                reset_sc = QtWidgets.QShortcut(reset_seq, main_window)
                reset_sc.activated.connect(lambda: _set_zoom(webview, 1.0))
            except Exception:
                pass
        else:
            print("chart_page: No webview available (PyQt6 WebEngine not installed?)")
    except Exception as e:
        print("chart_page.setup failed:", e)


def _set_zoom(webview, factor: float):
    try:
        if hasattr(webview, "setZoomFactor"):
            webview.setZoomFactor(factor)
            return
        if hasattr(webview, "page") and hasattr(webview.page(), "setZoomFactor"):
            webview.page().setZoomFactor(factor)
            return
        if hasattr(webview, "runJavaScript"):
            js = f"document.body.style.zoom = '{int(factor*100)}%';"
            webview.runJavaScript(js)
    except Exception as e:
        print("chart_page: Error setting zoom:", e)


def _change_zoom(webview, delta: float):
    try:
        current = None
        if hasattr(webview, "zoomFactor"):
            current = webview.zoomFactor()
        elif hasattr(webview, "page") and hasattr(webview.page(), "zoomFactor"):
            current = webview.page().zoomFactor()
        if current is None:
            current = 1.0
        new = max(0.1, current + delta)
        _set_zoom(webview, new)
    except Exception as e:
        print("chart_page: Error changing zoom:", e)
