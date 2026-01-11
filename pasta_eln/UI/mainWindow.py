""" Graphical user interface houses all widgets """
import json
import logging
import re
import sys
import webbrowser
from enum import Enum
from pathlib import Path
from typing import Any
from PySide6.QtCore import QEvent, QObject, QPropertyAnimation, QRect, QUrl, Slot, Qt
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QMouseEvent, QPixmap, QShortcut, QPainter
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QPushButton
import qtawesome as qta
from pasta_eln import __version__
from ..backendWorker.worker import Task
from ..fixedStringsJson import CONF_FILE_NAME, AboutMessage, shortcuts
from ..miscTools import hardRestart, installPythonPackages, updateAddOnList
from .body import Body
from .config.main import Configuration
from .data_hierarchy.editor import SchemeEditor
from .definitions.editor import Editor as DefinitionsEditor
from .form import Form
from .guiCommunicate import Communicate
from .guiStyle import Action, IconButton, ScrollMessageBox, widgetAndLayout
from .messageDialog import showMessage
from .palette import Palette
from .repositories.uploadGUI import UploadGUI
from .sidebar import Sidebar


class VerticalLabel(QLabel):
  """Label with vertical text"""
  def __init__(self, text: str, parent=None):
    super().__init__(text, parent)
    self.setAlignment(Qt.AlignmentFlag.AlignCenter)
  
  def paintEvent(self, event):
    # Log that paintEvent is being called
    logging.debug(f'VerticalLabel paintEvent called: text="{self.text()}", size={self.width()}x{self.height()}, visible={self.isVisible()}')
    
    painter = QPainter(self)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Get text to display
    text = self.text()
    if not text:
      logging.debug('VerticalLabel: No text to display')
      return
    
    # Get label dimensions
    w = self.width()
    h = self.height()
    
    if w <= 0 or h <= 0:
      logging.debug(f'VerticalLabel: Invalid size {w}x{h}')
      return
    
    # Get text color - always use white for visibility
    textColor = QColor(255, 255, 255)
    painter.setPen(textColor)
    
    # Set up font
    font = self.font()
    font.setBold(True)
    font.setPointSize(12)
    painter.setFont(font)
    
    # Rotate the painter 270 degrees around the center so text reads from bottom to top
    painter.save()
    # Translate to center
    painter.translate(w / 2, h / 2)
    # Rotate 270 degrees (or -90)
    painter.rotate(270)
    # Translate back - after rotation, width and height are swapped
    painter.translate(-h / 2, -w / 2)
    
    # Draw the text - after rotation, we draw in the swapped coordinate system
    # The text rectangle is now h (height) wide and w (width) tall
    painter.drawText(0, 0, h, w, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()
    
    logging.debug(f'VerticalLabel: Text drawn successfully')


class MainWindow(QMainWindow):
  """ Graphical user interface includes all widgets """

  def __init__(self, comm:Communicate) -> None:
    """ Init main window
    Args:
      projectGroup (str): project group to load
    """
    # global setting
    super().__init__()
    self.comm = comm
    if self.comm.configuration:
      self.comm.palette = Palette(self, self.comm.configuration['GUI']['theme'])
      self.comm.docTypesChanged.connect(self.paint)
    else:
      configWindow = Configuration(self.comm, 'setup')
      configWindow.exec()
      self.setCentralWidget(QLabel('ERROR: No configuration present!'))
      return
    # Initialize sidebar state early, before connecting signals
    self.sidebarHidden = False
    
    self.comm.formDoc.connect(self.formDoc)
    self.comm.changeSidebar.connect(self.paint)
    self.comm.backendThread.worker.beSendTaskReport.connect(self.showReport)
    self.comm.changeProject.connect(self.onProjectChanged)
    self.comm.changeTable.connect(self.onTableChanged)

    # GUI
    self.setWindowTitle(f"PASTA-ELN {__version__}")
    self.resize(self.screen().size())                                 #self.setWindowState(Qt.WindowMaximized)
    #TODO https://bugreports.qt.io/browse/PYSIDE-2706 https://bugreports.qt.io/browse/QTBUG-124892
    resourcesDir = Path(__file__).parent / 'Resources'
    self.setWindowIcon(QIcon(QPixmap(resourcesDir / 'Icons' / 'favicon64.png')))
    menu = self.menuBar()
    projectMenu = menu.addMenu('&Project')
    Action('&Export project to .eln',        self, [Command.EXPORT],         projectMenu)
    Action('&Import .eln into project',      self, [Command.IMPORT],         projectMenu)
    Action('&Upload to repository',          self, [Command.REPOSITORY],     projectMenu)
    Action('&Exit',                          self, [Command.EXIT],           projectMenu)

    self.viewMenu = menu.addMenu('Common &Lists')

    systemMenu = menu.addMenu('Project &group')
    self.changeProjectGroups = systemMenu.addMenu('&Change project group')
    syncMenu = systemMenu.addMenu('&Synchronize')
    Action('Send',                         self, [Command.SYNC_SEND],        syncMenu, shortcut='F5')
    if 'develop' in self.comm.configuration:
      Action('Get',                          self, [Command.SYNC_GET],       syncMenu, shortcut='F4')
      # Action('Smart synce',                  self, [Command.SYNC_SMART],       syncMenu)
    Action('&Item type editor',              self, [Command.SCHEMA],         systemMenu, shortcut='F8')
    Action('&Definitions editor',            self, [Command.DEFINITIONS],    systemMenu)
    systemMenu.addSeparator()
    Action('&Test extraction from a file',   self, [Command.TEST1],          systemMenu)
    Action('Test &selected item extraction', self, [Command.TEST2],          systemMenu, shortcut='F2')
    Action('Update &Add-on list',            self, [Command.UPDATE],         systemMenu)
    if 'develop' in self.comm.configuration:
      systemMenu.addSeparator()
      Action('&Verify database',             self, [Command.CHECK_DB],       systemMenu, shortcut='Ctrl+?')

    helpMenu = menu.addMenu('&Other')
    Action('&Website',                       self, [Command.WEBSITE],        helpMenu)
    Action('Shortcuts',                      self, [Command.SHORTCUTS],      helpMenu)
    Action('About',                          self, [Command.ABOUT],          helpMenu)
    systemMenu.addSeparator()
    Action('&Configuration',                 self, [Command.CONFIG],         helpMenu, shortcut='Ctrl+0')

    # shortcuts for advanced usage (user should not need)
    QShortcut('F9', self, lambda: self.execute([Command.RESTART]))
    if 'develop' not in self.comm.configuration:
      QShortcut('Ctrl+?', self, lambda: self.execute([Command.CHECK_DB]))

    # GUI elements
    mainWidget, mainLayout = widgetAndLayout('H')
    self.setCentralWidget(mainWidget)                                   # Set the central widget of the Window
    body = Body(self.comm)                                                             # body with information
    # Add body to layout (sidebar will be overlaid on top, not in layout)
    mainLayout.addWidget(body)
    
    # Create sidebar as overlay widget (not in layout, so it doesn't move other panels)
    self.sidebar = Sidebar(self.comm, mainWindow=self)
    self.sidebar.setParent(mainWidget)  # Set parent but don't add to layout
    # Position sidebar initially (will be updated on show/resize)
    sidebarWidth = self.comm.configuration['GUI']['sidebarWidth']
    self.sidebar.setGeometry(0, 0, sidebarWidth, mainWidget.height())
    self.sidebar.raise_()  # Ensure it's on top
    # Hide sidebar initially - tab will be shown instead
    self.sidebar.hide()
    
    # Create sidebar tab button (appears when sidebar is hidden)
    # The button will be the whole tab, with text inside
    self.sidebarTab = QPushButton(self)
    # Put text directly on button - simpler approach
    self.sidebarTab.setText('P\nr\no\nj\ne\nc\nt\ns')  # Vertical text using newlines
    self.sidebarTab.setToolTip('Show project list')
    # Button size will be set dynamically to cover the whole tab area
    self.sidebarTab.setStyleSheet("""
      QPushButton {
        background-color: rgba(100, 100, 100, 200);
        border: 1px solid rgba(150, 150, 150, 255);
        border-left: none;
        border-radius: 0px 8px 8px 0px;
        padding: 2px;
        color: white;
        font-weight: bold;
        font-size: 12px;
      }
      QPushButton:hover {
        background-color: rgba(120, 120, 120, 220);
      }
    """)
    self.sidebarTab.clicked.connect(self.showSidebar)
    # Set initial position off-screen so it doesn't appear at (0,0) before positioning
    self.sidebarTab.setGeometry(-100, -100, 40, 120)  # Position off-screen initially (updated to match new size)
    self.sidebarTab.hide()  # Initially hidden
    self.sidebarTab.raise_()  # Make sure it's on top
    
    # Create label with vertical text (will be positioned on top of button)
    self.sidebarTabLabel = VerticalLabel('Projects', self)
    # Ensure text is set
    self.sidebarTabLabel.setText('Projects')
    # Set white text color explicitly
    self.sidebarTabLabel.setStyleSheet("""
      QLabel {
        background-color: transparent;
        color: white;
        font-weight: bold;
        font-size: 12px;
      }
    """)
    # Ensure label is visible and on top
    self.sidebarTabLabel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)  # Allow clicks to pass through to button
    # Set minimum size to ensure it can be painted
    self.sidebarTabLabel.setMinimumSize(100, 30)
    # Set initial position off-screen
    self.sidebarTabLabel.setGeometry(-100, -100, 100, 30)  # Position off-screen initially
    self.sidebarTabLabel.hide()  # Initially hidden
    # Make sure label is always on top of button
    self.sidebarTabLabel.setParent(self)
    self.sidebarTabLabel.raise_()
    # Ensure the label is enabled and can be painted
    self.sidebarTabLabel.setEnabled(True)
    # Set visible flag (will be shown when sidebar is hidden)
    self.sidebarTabLabel.setVisible(False)
    
    # Auto-hide sidebar functionality
    # Start with sidebar hidden and tab shown
    self.sidebarHidden = True
    self.hoverZoneWidth = 10  # Width of hover zone on left border
    self.setMouseTracking(True)  # Enable mouse tracking for the main window
    mainWidget.setMouseTracking(True)  # Enable mouse tracking for central widget
    body.setMouseTracking(True)  # Enable mouse tracking for body
    
    # Animation for sidebar show/hide
    # Use custom animatedWidth property for overlay mode
    self.sidebarAnimation = QPropertyAnimation(self.sidebar, b"animatedWidth")
    self.sidebarAnimation.setDuration(200)  # 200ms animation
    # Connect animation to update tab position
    self.sidebarAnimation.valueChanged.connect(self.updateTabPositionWithSidebar)
    
    # Show the tab initially since sidebar is hidden
    self.updateSidebarTabPosition()
    if self.sidebarTab.geometry().y() >= 0:
      self.sidebarTab.show()
      self.sidebarTab.raise_()
      if hasattr(self, 'sidebarTabLabel'):
        self.sidebarTabLabel.show()
        self.sidebarTabLabel.setVisible(True)
        self.sidebarTabLabel.raise_()
        self.sidebarTabLabel.update()
        self.sidebarTabLabel.repaint()
    
    # Install event filter on body and sidebar to detect mouse movements
    body.installEventFilter(self)
    self.sidebar.installEventFilter(self)
    
    self.paint()


  @Slot(str, str)
  def onProjectChanged(self, projID: str, item: str) -> None:
    """
    Handle project change - hide sidebar when a specific project is opened
    
    Args:
      projID (str): project ID
      item (str): item ID
    """
    if projID and projID != '':
      # A specific project is opened, hide sidebar
      self.hideSidebar()
    else:
      # No project selected, show sidebar
      self.showSidebar()
  
  @Slot(str, str)
  def onTableChanged(self, docType: str, projectID: str) -> None:
    """
    Handle table change - show sidebar when viewing project list
    
    Args:
      docType (str): document type
      projectID (str): project ID
    """
    if docType == 'x0' or not projectID or projectID == '':
      # Viewing project list or no project, show sidebar
      self.showSidebar()
    else:
      # Viewing a specific project's table, hide sidebar
      self.hideSidebar()
  
  def hideSidebar(self) -> None:
    """Hide the sidebar with animation"""
    # Safety check - initialize if not already set
    if not hasattr(self, 'sidebarHidden'):
      self.sidebarHidden = False
    if not self.sidebarHidden:
      self.sidebarHidden = True
      currentWidth = self.sidebar._animatedWidth if hasattr(self.sidebar, '_animatedWidth') else (self.sidebar.width() if self.sidebar.width() > 0 else self.comm.configuration['GUI']['sidebarWidth'])
      self.sidebarAnimation.setStartValue(currentWidth)
      self.sidebarAnimation.setEndValue(0)
      self.sidebarAnimation.start()
      # Don't hide immediately - let animation complete
      # The sidebar will be hidden when animation finishes (width becomes 0)
      # Position the tab button first, then show it
      self.updateSidebarTabPosition()
      # Only show if position was successfully calculated (y >= 0 means valid position)
      if self.sidebarTab.geometry().y() >= 0:
        self.sidebarTab.show()
        self.sidebarTab.raise_()
        # Also show label if it exists (for backward compatibility)
        if hasattr(self, 'sidebarTabLabel'):
          self.sidebarTabLabel.show()
          self.sidebarTabLabel.setVisible(True)
          self.sidebarTabLabel.raise_()
          self.sidebarTabLabel.update()
          self.sidebarTabLabel.repaint()
  
  def showSidebar(self) -> None:
    """Show the sidebar with animation"""
    # Safety check - initialize if not already set
    if not hasattr(self, 'sidebarHidden'):
      self.sidebarHidden = False
    if self.sidebarHidden:
      self.sidebarHidden = False
      sidebarWidth = self.comm.configuration['GUI']['sidebarWidth']
      
      # Position sidebar absolutely at left edge (overlay style)
      mainWidget = self.centralWidget()
      if mainWidget:
        sidebarHeight = mainWidget.height()
        self.sidebar.setGeometry(0, 0, sidebarWidth, sidebarHeight)
        # Initialize animated width
        self.sidebar._animatedWidth = 0  # Start from 0 for animation
      
      self.sidebar.show()
      self.sidebar.raise_()  # Ensure sidebar is on top
      # Position tab at the right edge of sidebar initially
      self.updateSidebarTabPosition()
      if self.sidebarTab.geometry().y() >= 0:
        self.sidebarTab.show()
        self.sidebarTab.raise_()
        if hasattr(self, 'sidebarTabLabel'):
          self.sidebarTabLabel.show()
          self.sidebarTabLabel.raise_()
      # Start animation - tab will move with sidebar via updateTabPositionWithSidebar
      self.sidebarAnimation.setStartValue(0)
      self.sidebarAnimation.setEndValue(sidebarWidth)
      self.sidebarAnimation.start()
  
  def updateTabPositionWithSidebar(self, width: int) -> None:
    """Update tab position as sidebar animates"""
    if not hasattr(self, 'sidebarTab') or not self.sidebarTab:
      return
    # Move tab to follow the sidebar's right edge
    if self.sidebar.isVisible():
      # Tab should be at the right edge of the sidebar
      tabY = self.sidebarTab.geometry().y()
      if tabY < 0:
        # Tab not positioned yet, get position from updateSidebarTabPosition
        self.updateSidebarTabPosition()
        tabY = self.sidebarTab.geometry().y()
      if tabY >= 0:  # Only update if tab is visible
        self.sidebarTab.setGeometry(width, tabY, self.sidebarTab.width(), self.sidebarTab.height())
        # Update label position too
        if hasattr(self, 'sidebarTabLabel') and self.sidebarTabLabel:
          labelX = width + (self.sidebarTab.width() - self.sidebarTabLabel.width()) // 2
          labelY = self.sidebarTabLabel.geometry().y()
          self.sidebarTabLabel.setGeometry(labelX, labelY, self.sidebarTabLabel.width(), self.sidebarTabLabel.height())
    else:
      # Sidebar is hidden, move tab to left edge
      tabY = self.sidebarTab.geometry().y()
      if tabY >= 0:
        self.sidebarTab.setGeometry(0, tabY, self.sidebarTab.width(), self.sidebarTab.height())
        if hasattr(self, 'sidebarTabLabel') and self.sidebarTabLabel:
          labelX = (self.sidebarTab.width() - self.sidebarTabLabel.width()) // 2
          labelY = self.sidebarTabLabel.geometry().y()
          self.sidebarTabLabel.setGeometry(labelX, labelY, self.sidebarTabLabel.width(), self.sidebarTabLabel.height())
  
  def updateSidebarTabPosition(self) -> None:
    """Update the position of the sidebar tab button"""
    if not self.sidebarTab or not self.sidebarTabLabel:
      return
      
    # Always update position, even if not visible yet (so it's ready when shown)
    # Position tab on left edge at 1/3 of window height from top
    # Use geometry() to get actual window size, accounting for frame
    windowGeometry = self.geometry()
    windowHeight = windowGeometry.height()
    
    # If window height is too small, don't position (wait for proper size)
    if windowHeight < 200:
      return
    
    menuBarHeight = self.menuBar().height() if self.menuBar() else 0
    availableHeight = windowHeight - menuBarHeight
    
    # Tab dimensions - make it wide enough to be the whole tab
    tabWidth = 40  # Width of the tab (increased from 30)
    tabHeight = 120  # Height of the tab (increased from 100)
    
    # Position at 1/3 of available height from top
    # Use window-relative coordinates (0, 0 is top-left of window content area)
    tabY = menuBarHeight + (availableHeight // 3) - (tabHeight // 2)
    # Ensure tab doesn't go outside window bounds
    tabY = max(menuBarHeight, min(tabY, windowHeight - tabHeight))
    
    # Set button position - if sidebar is visible, position at right edge of sidebar
    # Otherwise, position at left edge (x=0)
    if hasattr(self, 'sidebar') and self.sidebar and self.sidebar.isVisible():
      sidebarX = self.sidebar.x() + self.sidebar.width()
      tabX = sidebarX
    else:
      tabX = 0
    
    self.sidebarTab.setGeometry(tabX, tabY, tabWidth, tabHeight)
    
    # Position the vertical text label to cover the entire button area
    # The label will be rotated 270 degrees, so width/height are swapped
    # Button is 40x120, so label should be 120x40 (swapped) to fill the button after rotation
    # After 270° rotation: label width becomes text height, label height becomes text width
    labelWidth = tabHeight  # 120 - label width (becomes height of rotated text)
    labelHeight = tabWidth  # 40 - label height (becomes width of rotated text)
    # Center the label on the button - use button's position
    buttonX = self.sidebarTab.x()
    buttonY = self.sidebarTab.y()
    # Center horizontally and vertically on the button
    labelX = buttonX + (self.sidebarTab.width() - labelHeight) // 2
    labelY = buttonY + (self.sidebarTab.height() - labelWidth) // 2
    # Adjust vertical position to move text slightly (e.g., move it up by a few pixels)
    # This centers the text better within the tab
    labelY = buttonY + (self.sidebarTab.height() - labelWidth) // 2 - 2  # Move up 2px for better centering
    # setGeometry(x, y, width, height) - label is 100 wide, 30 tall
    self.sidebarTabLabel.setGeometry(labelX, labelY, labelWidth, labelHeight)
    # Ensure label is updated and repainted after positioning
    if self.sidebarTabLabel.isVisible():
      self.sidebarTabLabel.update()
      self.sidebarTabLabel.repaint()
  
  def eventFilter(self, obj: QObject, event: QEvent) -> bool:
    """
    Filter events to detect mouse near left border
    
    Args:
      obj: object that received the event
      event: event
      
    Returns:
      bool: True if event was handled
    """
    if event.type() == QEvent.Type.MouseMove:
      mouseEvent = QMouseEvent(event)
      # Get mouse position relative to main window
      mousePos = self.mapFromGlobal(mouseEvent.globalPosition().toPoint())
      mouseX = mousePos.x()
      sidebarWidth = self.comm.configuration['GUI']['sidebarWidth']
      
      # If mouse is over sidebar, keep it visible
      if obj == self.sidebar:
        # Safety check
        if not hasattr(self, 'sidebarHidden'):
          self.sidebarHidden = False
        if self.sidebarHidden and self.comm.projectID and self.comm.projectID != '':
          self.showSidebar()
        return False  # Let sidebar handle its own events
      
      # Only handle auto-hide/show if a project is open
      if self.comm.projectID and self.comm.projectID != '':
        # Safety check
        if not hasattr(self, 'sidebarHidden'):
          self.sidebarHidden = False
        if self.sidebarHidden:
          # Sidebar is hidden - show it if mouse is near left border
          if mouseX <= self.hoverZoneWidth:
            self.showSidebar()
        else:
          # Sidebar is visible - hide it if mouse moved away from sidebar and hover zone
          if mouseX > sidebarWidth + self.hoverZoneWidth:
            self.hideSidebar()
    
    return super().eventFilter(obj, event)

  @Slot(str)
  def paint(self, _:str='') -> None:
    """ Process things that might change """
    # Things that are inside the List menu
    self.viewMenu.clear()
    for key, value in self.comm.docTypesTitles.items():
      shortcut = None if value['shortcut']=='' else f"Ctrl+{value['shortcut']}"
      Action(value['title'],            self, [Command.VIEW, key],  self.viewMenu, shortcut=shortcut)
    self.viewMenu.addSeparator()
    Action('&Tags',               self, [Command.VIEW, '_tags_'], self.viewMenu, shortcut='Ctrl+T')
    Action('&Unidentified',       self, [Command.VIEW, '-'],      self.viewMenu, shortcut='Ctrl+U')
    # Things that are related to project group
    self.changeProjectGroups.clear()
    for name in self.comm.configuration['projectGroups'].keys():
      Action(name,                         self, [Command.CHANGE_PG, name], self.changeProjectGroups)
    return


  def resizeEvent(self, event) -> None:
    """Handle window resize - update sidebar tab position"""
    super().resizeEvent(event)
    # Update sidebar position if it's visible (overlay style)
    if hasattr(self, 'sidebar') and self.sidebar and self.sidebar.isVisible():
      mainWidget = self.centralWidget()
      if mainWidget:
        sidebarWidth = self.comm.configuration['GUI']['sidebarWidth']
        sidebarHeight = mainWidget.height()
        self.sidebar.setGeometry(0, 0, sidebarWidth, sidebarHeight)
    
    # Always update tab position on resize if sidebar is hidden
    if self.sidebarHidden and hasattr(self, 'sidebarTab') and self.sidebarTab:
      self.updateSidebarTabPosition()
      # Force label to repaint on resize
      if hasattr(self, 'sidebarTabLabel') and self.sidebarTabLabel and self.sidebarTabLabel.isVisible():
        self.sidebarTabLabel.update()
  
  def closeEvent(self, event:QEvent) -> None:
    """
    Handle window close event - cleanup of backend thread

    Args:
      event: close event
    """
    if self.comm and hasattr(self.comm, 'backendThread') and self.comm.backendThread:
      self.comm.shutdownBackendThread()
    event.accept()


  @Slot(dict)
  def formDoc(self, doc: dict[str, Any]) -> None:
    """
    What happens when new/edit dialog is shown

    Args:
      doc (dict): document
    """
    formWindow = Form(self.comm, doc)
    ret = formWindow.exec()
    if ret == 0:
      self.comm.stopSequentialEdit.emit()
    return


  def execute(self, command: list[Any]) -> None:
    """
    action after clicking menu item
    """
    # file menu
    if command[0] is Command.EXPORT:
      if self.comm.projectID == '':
        showMessage(self, 'Error', 'You have to open a project to export', 'Critical')
        return
      fileName = QFileDialog.getSaveFileName(self, 'Save project into .eln file', str(Path.home()), '*.eln')[0]
      if fileName != '':
        docTypes = [i for i in self.comm.docTypesTitles if i[0]!='x']
        self.comm.uiRequestTask.emit(Task.EXPORT_ELN, {'fileName':fileName, 'projID':self.comm.projectID, 'docTypes':docTypes})
    elif command[0] is Command.IMPORT:
      if self.comm.projectID == '':
        showMessage(self, 'Error', 'You have to open a project to import', 'Critical')
        return
      fileName = QFileDialog.getOpenFileName(self, 'Load data from .eln file', str(Path.home()), '*.eln')[0]
      if fileName != '':
        self.comm.uiRequestTask.emit(Task.IMPORT_ELN, {'fileName':fileName, 'projID':self.comm.projectID})
        self.comm.changeProject.emit(self.comm.projectID, '')
    elif command[0] is Command.REPOSITORY:
      if self.comm.projectID == '':
        showMessage(self, 'Error', 'You have to open a project to upload', 'Critical')
        return
      dialogR = UploadGUI(self.comm)
      dialogR.exec()
    elif command[0] is Command.EXIT:
      self.close()
    # view menu
    elif command[0] is Command.VIEW:
      self.comm.projectID = ''
      self.comm.changeTable.emit(command[1], '')
      self.comm.changeSidebar.emit('')
    # system menu
    elif command[0] is Command.CHANGE_PG:
      self.comm.configuration['defaultProjectGroup'] = command[1]
      with open(Path.home()/CONF_FILE_NAME, 'w', encoding='utf-8') as fConf:
        fConf.write(json.dumps(self.comm.configuration, indent=2))
      self.comm.projectGroup = command[1]
      self.comm.start(command[1])
    elif command[0] is Command.SYNC_SEND:
      self.comm.uiRequestTask.emit(Task.SEND_ELAB,  {'projGroup':self.comm.projectGroup})
    elif command[0] is Command.SYNC_GET:
      self.comm.uiRequestTask.emit(Task.GET_ELAB,   {'projGroup':self.comm.projectGroup})
    elif command[0] is Command.SYNC_SMART:
      self.comm.uiRequestTask.emit(Task.SMART_ELAB, {'projGroup':self.comm.projectGroup})
    elif command[0] is Command.SCHEMA:
      dialogS = SchemeEditor(self.comm)
      dialogS.exec()
    elif command[0] is Command.DEFINITIONS:
      dialogD = DefinitionsEditor(self.comm)
      dialogD.show()
    elif command[0] is Command.TEST1:
      fileName = QFileDialog.getOpenFileName(self, 'Open file for extractor test', str(Path.home()), '*.*')[0]
      if fileName is not None:
        self.comm.uiRequestTask.emit(Task.EXTRACTOR_TEST, {'fileName':fileName, 'style':'html', 'recipe':'', 'saveFig':''})
    elif command[0] is Command.TEST2:
      self.comm.testExtractor.emit()
    elif command[0] is Command.UPDATE:
      configProjecGroup = self.comm.configuration['projectGroups'][self.comm.projectGroup]
      installPythonPackages(configProjecGroup['addOnDir'])
      reportDict = updateAddOnList(self.comm.projectGroup)
      messageWindow = ScrollMessageBox('Add-on list updated', {'main':reportDict},
                                       style='QScrollArea{min-width:600 px; min-height:400px}')
      messageWindow.exec()
      hardRestart()
    elif command[0] is Command.CONFIG:
      dialogC = Configuration(self.comm)
      dialogC.exec()
    # remainder
    elif command[0] is Command.WEBSITE:
      webbrowser.open('https://pasta-eln.github.io/pasta-eln/')
    elif command[0] is Command.CHECK_DB:
      self.comm.uiRequestTask.emit(Task.CHECK_DB, {'style':'html'})
    elif command[0] is Command.SHORTCUTS:
      showMessage(self, 'Keyboard shortcuts', shortcuts, 'Information')
    elif command[0] is Command.ABOUT:
      showMessage(self, 'About', f'{AboutMessage}Environment: {sys.prefix}\n','Information')
    elif command[0] is Command.RESTART:
      hardRestart()
    else:
      logging.error('Gui menu unknown: %s', command, exc_info=True)
    return


  @Slot(Task, str, str, str)
  def showReport(self, task:Task, reportText:str, image:str, path:str) -> None:
    """ Show a report from backend worker
    Args:
      task (Task): task name
      reportText (str): text of the report
      image (str): base64 encoded image, svg image
      path (str): path to the file/folder that should be opened
    """
    if task is Task.OPEN_EXTERNAL and path:
      QDesktopServices.openUrl(QUrl.fromLocalFile(path))
      return
    if task in (Task.SCAN, Task.DROP_EXTERNAL):
      self.comm.changeProject.emit(self.comm.projectID, '')
    elif task is Task.CHECK_DB:
      regexStr = r'<font color="magenta">image does not exist m-[0-9a-f]+ image: comment:<\/font><br>'
      myCount = len(re.findall(regexStr, reportText))
      if myCount>5:
        reportText = re.sub(regexStr, '', reportText, count=myCount-5)
        reportText += r'<font color="magenta">image does not exist ...:<\/font><br>'
    elif task not in (Task.EXTRACTOR_TEST, Task.EXTRACTOR_RERUN, Task.DELETE_DOC, Task.EXPORT_ELN, Task.IMPORT_ELN, Task.SEND_ELAB,
                      Task.GET_ELAB, Task.SMART_ELAB):               #e.g. extractor tests work out of the box
      logging.error('Unknown task in showReport: %s', task, exc_info=True)
    showMessage(self, 'Report', reportText, image=image)


class Command(Enum):
  """ Commands used in this file """
  EXPORT     = 1
  IMPORT     = 2
  EXIT       = 3
  VIEW       = 4
  CHANGE_PG  = 6
  SYNC_SEND  = 7
  SYNC_GET   = 8
  SYNC_SMART = 9
  SCHEMA     = 10
  TEST1      = 11
  TEST2      = 12
  UPDATE     = 13
  CONFIG     = 14
  WEBSITE    = 15
  CHECK_DB   = 16
  SHORTCUTS  = 17
  RESTART    = 18
  ABOUT      = 19
  DEFINITIONS= 20
  REPOSITORY = 21
