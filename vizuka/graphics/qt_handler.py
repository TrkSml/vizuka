"""
Qt handler for drawing buttons and IHM black magic.
Please do read it you fool. I must admit I am not
proud of everything written down there.

This should be rewritten with QtCreator's help.
"""
import matplotlib
import sys
import logging
import os

matplotlib.use('Qt5Agg')  # noqa
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.gridspec as gridspec

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSizePolicy,
    QDockWidget,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QAction,
    QMenu,
    QFileDialog,
    QDialog,
)

from vizuka.graphics import qt_helpers
from vizuka.cluster_diving import moar_filters
from vizuka import clustering
from vizuka import frontier
from vizuka.cluster_viewer import make_plotter


def onclick_wrapper(onclick):
    """
    This decorator for onclick detects if the mouse event
    should trigger something.
    I tried to make it worst but this is my best
    """
    def wrapper(*args, **kwargs):
        if args[0].detect_mouse_event:  # args[0] is self
            return onclick(*args, **kwargs)
        else:
            return lambda x: None
    return wrapper

CLUSTER_PLOTTER = {}
            
class Cluster_viewer(matplotlib.figure.Figure):

    def __init__(self, features_to_display, x_raw, x_raw_columns, show_dichotomy=True):
        super().__init__()
        self.x_raw = x_raw
        self.x_raw_columns = x_raw_columns
        self.show_dichotomy = show_dichotomy # deprecated

        self.features_to_display = features_to_display
        self.spec_by_name = {}
        self.cluster_view_selected_indexes = []

        self.spec = gridspec.GridSpec(
                len(features_to_display.keys()),
                2, wspace=0.2
                )
        
        for idx,feature_name in enumerate(features_to_display.keys()):
            for plotter in features_to_display[feature_name]:
                self.spec_by_name[feature_name+plotter] = {}
                self.spec_by_name[feature_name+plotter]['good'] = self.spec[idx%2]
                self.spec_by_name[feature_name+plotter]['bad' ] = self.spec[idx%2+1]

                if plotter not in CLUSTER_PLOTTER.keys():
                    CLUSTER_PLOTTER[plotter] = make_plotter(plotter)
       
    def update_cluster_view(self, index_good, index_bad, data_by_index):
        """
        Updates the axes with the data of the selected cluster

        index_good: indexes of all good predictions
        index_bad: indexes of all bad predicitons
        data_by_index: data
        """
        self.clear()
        self.cluster_view_selected_indexes = set(index_good+index_bad)
        
        
        selected_xs_raw  ={}
        data_to_display = {}

        if self.show_dichotomy:
            selected_xs_raw['good'] = [
                    data_by_index[idx] for idx in self.cluster_view_selected_indexes if idx in index_good]
            selected_xs_raw['bad' ] = [
                    data_by_index[idx] for idx in self.cluster_view_selected_indexes if idx in index_bad ]
        else:
            selected_xs_raw['all'] = [
                    data_by_index[idx] for idx in self.cluster_view_selected_indexes]

        columns_to_display = [list(self.x_raw_columns).index(i) for i in self.features_to_display]
        if self.show_dichotomy:
            data_to_display['good'] = {
                self.x_raw_columns[i]:[x[i] for x in selected_xs_raw['good']]
                for i in columns_to_display
                }
            data_to_display['bad'] = {
                self.x_raw_columns[i]:[x[i] for x in selected_xs_raw['bad']]
                for i in columns_to_display
                }
        else:
            data_to_display['all'] = {
                    self.x_raw_columns[i]:[x[i] for x in selected_xs_raw['all']]
                    for i in columns_to_display
                    }

        def plot_it(plotter, plotter_name, data_to_display, data_name, fig, spec_to_update_, key):

            spec_to_update = spec_to_update_[key]
            data = data_to_display[key][data_name]
            axe = plotter(data, fig, spec_to_update)
            if 'log' in plotter_name:
                data_name += ' - log'
            data_name +=  ' - {} predictions'.format(key)
            if axe:
                axe.set_title(data_name)

        for key in ['good', 'bad']:
            for data_name in self.features_to_display:
                for plotter_name in self.features_to_display[data_name]:
                    plotter = CLUSTER_PLOTTER[plotter_name]
                    spec_to_update = self.spec_by_name[data_name+plotter_name]
                    plot_it(plotter, plotter_name, data_to_display, data_name, self, spec_to_update, key) 

        
    def reset(self):
        self.clear()
        self.cluster_view_selected_indexes = []


class Qt_matplotlib_handler():

    def __init__(self, figure):
        self.right_dock = QtCore.Qt.RightDockWidgetArea
        self.textboxs = {}
        self.plottings = []

        # configure the app + main window
        self.app = QApplication(sys.argv)
        self.window = QMainWindow()
        self.features_to_filter=None
        self.figure = figure


    def show(self):
        """
        Shows the window you built with your tears
        """
        self.window.showMaximized()
        for win in self.additional_windows:
            win.show()
        self.refresh()
        logging.info("refreshed")
        logging.info("showed")

    def refresh(self):
        """
        Refresh the matplotlib plots
        """
        for plotting in self.plottings:
            try:
                plotting.canvas.draw()
            except ValueError as e:
                # This exception is raised when nothing to be draw
                logging.warn(e)
                for i in self.figure.get_axes():
                    i.clear()
                
    
    @onclick_wrapper
    def onclick(self, *args, **kwargs):
        """
        ..seealso::onclick_wrapper
        """
        self.base_onclick(*args, **kwargs)

        
    def toogle_detect_mouse_event(self, *args, **kwargs):
        """
        Enable/Disable mouse_event handling ..seealso::onclick_wrapper
        """
        self.detect_mouse_event = not self.detect_mouse_event


class Viz_handler(Qt_matplotlib_handler):
    """
    A Viz_handler is attached to the viz_engine defined in vizualization.py
    It basically lists lots of QWidget things and propose methods to init
    them "gracefully", hum...

    Only IHM here.
    """
    
    def __init__(
            self,
            viz_engine,
            figure,
            onclick,
            additional_filters=[],
            additional_figures=[],
            ):
        """
        This object is a QtWindow (or 2-3-4...) with a mamtplotlib.Figure
        and a onclick event handler. As you can see it is also linked to
        a viz_engine which will do the magic.
        
        This instance should only do IHM stuff, nothing intellectual, everything
        is handled by the viz_engine
        """
        super(Viz_handler, self).__init__(figure)

        self.viz_engine = viz_engine
        self.detect_mouse_event = True
        self.base_onclick = onclick
        self.window.setWindowTitle('Data vizualization')
        self.additional_filters = additional_filters
        self.additional_figures = additional_figures

        self.additional_windows = []

        # add the main figure
        qt_helpers.add_figure(self.figure, window=self.window, plottings=self.plottings, onclick=self.onclick)
        #self.cluster_diver = Cluster_diver(self.x_raw, self.x_raw_columns, ['ape_code'])

        # add additional window
        if self.additional_filters:
            self.additional_windows.append(qt_helpers.add_window(self.window, 'moar filters'))
            moar_filters(
                    window=self.additional_windows[-1],
                    right_dock=QtCore.Qt.RightDockWidgetArea,
                    features = self.viz_engine.x_raw,
                    all_features_categories = self.viz_engine.x_raw_columns,
                    features_to_filter=additional_filters,
                    viz_engine=self.viz_engine,
                    )

        for fig in self.additional_figures:
            self.add_figure(fig, 'Cluster viewer')

        # self.add_figure(self.additional_figure, onclick=None, window=self.additional_window)
        self.initUI()

    def add_figure(self, fig, name):
        self.additional_windows.append(qt_helpers.add_window(self.window, name))
        qt_helpers.add_figure(fig, self.additional_windows[-1], plottings=self.plottings)

    
    def initUI(self):
        window = self.window
        
        window.statusBar().showMessage('Loading...')

        menubar  = window.menuBar()

        loadMenu = menubar.addMenu("Load")
        loadpredictionAction = QAction("Predictions set", window)
        loadpredictionAction.triggered.connect(self.load_prediction)
        loadMenu.addAction(loadpredictionAction)

        exportMenu = menubar.addMenu('Export')
        exportAct = QAction('Export in csv', window)
        exportAct.triggered.connect(self.export)
        exportMenu.addAction(exportAct)
        

        clusteringMenu = menubar.addMenu("Clustering")

        saveclustersAct = QAction('Save current clusters', window)
        saveclustersAct.triggered.connect(self.save_clusters)
        clusteringMenu.addAction(saveclustersAct)

        requestClusteringMenu = QMenu('Request clustering', window)
        builtin_cl, extra_cl = clustering.list_clusterizer()
        available_clustering_engines = {**builtin_cl, **extra_cl}
        for clustering_engine_name in available_clustering_engines.keys():
            clusteringAct = QAction(clustering_engine_name, window)
            clusteringAct.triggered.connect(
                    lambda x, name=clustering_engine_name:self.request_new_clustering(name))
            requestClusteringMenu.addAction(clusteringAct)
        clusteringMenu.addMenu(requestClusteringMenu)

        self.loadClusterMenu = QMenu('Load saved clusters', window)
        for cluster_name in self.viz_engine.saved_clusters:
            loadAct = QAction(cluster_name, window)
            loadAct.triggered.connect(
                    lambda x, name=cluster_name:self.viz_engine.load_clusterization(name))
            self.loadClusterMenu.addAction(loadAct)
        clusteringMenu.addMenu(self.loadClusterMenu)
        
        frontierMenu = menubar.addMenu('Cluster frontiers')
        builtin_fr, extra_fr = frontier.list_frontiers()
        available_frontiers = {**builtin_fr, **extra_fr}
        for frontier_name in available_frontiers.keys():
            frontierAct = QAction(frontier_name, window)
            frontierAct.triggered.connect(
                    lambda x, name=frontier_name:self.viz_engine.request_new_frontiers(name))
            frontierMenu.addAction(frontierAct)
        
        filterMenu = menubar.addMenu('Filters')

        trueClassFilter       = QMenu('Filter by true class', window)
        self.all_true_filters = []

        for cls in self.viz_engine.possible_outputs_list:
            name = cls if len(cls)<30 else str(cls[:29])+'...'
            f = QAction(name, window, checkable=True)
            f.setChecked(False)
            f.class_ = cls
            self.all_true_filters.append(f)
            f.triggered.connect(lambda x:self.viz_engine.filter_by_correct_class(self.all_true_filters))
            trueClassFilter.addAction(f)

        filterMenu.addMenu(trueClassFilter)
        
        predictClassFilter       = QMenu('Filter by predicted class', window)
        self.all_predicted_filters = []

        for cls in self.viz_engine.possible_outputs_list:
            name = cls if len(cls)<30 else str(cls[:29])+'...'
            f = QAction(name, window, checkable=True)
            f.setChecked(False)
            f.class_ = cls
            self.all_predicted_filters.append(f)
            f.triggered.connect(lambda x:self.viz_engine.filter_by_predicted_class(self.all_predicted_filters))
            predictClassFilter.addAction(f)

        filterMenu.addMenu(predictClassFilter)

        
        
        navigationMenu = menubar.addMenu('Navigation')
        mouseEnabledAction = QAction('Disable mouse click', window, checkable=True)
        mouseEnabledAction.setChecked = True
        mouseEnabledAction.triggered.connect(self.toogle_detect_mouse_event)
        navigationMenu.addAction(mouseEnabledAction)

        
    def is_ready(self):
        self.window.statusBar().showMessage('Ready')

    def load_prediction(self):
        prediction_filename = self.file_dialog(
                "Load prediction",
                self.viz_engine.model_path,
                "{} Npz file (*{}.npz)".format(self.viz_engine.version, self.viz_engine.version),
                )
        if prediction_filename:
            self.viz_engine.reload_predict(prediction_filename)
        

    def is_loading(self):
        self.window.statusBar().showMessage('Loading...')

    def pop_dialog(self, msg):
        popup = QMessageBox(self.window)
        popup.setText(msg)
        popup.exec_()

    def file_dialog(self, name, directory, filter):
        dialog = QFileDialog(self.window, name, directory, filter)
        if dialog.exec_() == QDialog.Accepted:
            return dialog.selectedFiles()[0]


    def save_clusters(self):
        text, validated = QInputDialog.getText(
                self.window,
                "YOLO", "Name for the clusters you selected ?"
                )
        if validated:
            if text == '':
                text = "clusters"
            cluster_name = self.viz_engine.save_clusterization(text)
            loadAct = QAction(cluster_name, self.window)
            loadAct.triggered.connect(lambda:self.viz_engine.load_clusterization(cluster_name))
            self.loadClusterMenu.addAction(loadAct)

    def export(self):
        text, validated = QInputDialog.getText(
                self.window,
                "YOLO", "Name for the exported csv ?"
                )
        if validated:
            if text == '':
                text = "export.csv"
        self.viz_engine.export(text)

    def request_new_clustering(self, clustering_engine_name):
        self.clustering_params={}
        for requested_param in clustering.get_required_arguments(clustering_engine_name):
            text, validated = QInputDialog.getText(
                    self.window,
                    "YOLO", requested_param+' ?'
                    )
            self.clustering_params[requested_param]=float(text)

        return self.viz_engine.request_new_clustering(clustering_engine_name, self.clustering_params)
