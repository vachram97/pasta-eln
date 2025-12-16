""" Central widget: everything that is not sidebar: switches between project-view and table-details """
from typing import Any
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget
from .details import Details
from .docTypes import DocTypes
from .guiCommunicate import Communicate
from .project import Project


class Body(QWidget):
  """ Central widget: everything that is not sidebar: switches between project-view and table-details """
  def __init__(self, comm:Communicate):
    super().__init__()
    self.comm = comm
    comm.changeTable.connect(self.changeTable)
    comm.changeProject.connect(self.changeProject)
    comm.changeDetails.connect(self.changeDetails)

    # Create details panel that will be shared
    self.details = Details(comm)
    
    # Create main content widgets
    self.docTypes = DocTypes(comm)
    self.project  = Project(comm)
    self.project.hide()
    
    # Track current view mode
    self.isProjectView = False
    
    # Create splitter for 50/50 layout
    self.splitter = QSplitter()
    self.splitter.setHandleWidth(10)
    self.splitter.setOrientation(Qt.Orientation.Horizontal)
    
    # Create container widgets for left and right sides
    self.leftWidget = QWidget()
    self.leftLayout = QVBoxLayout(self.leftWidget)
    self.leftLayout.setSpacing(0)
    self.leftLayout.setContentsMargins(0, 0, 0, 0)
    self.leftLayout.addWidget(self.docTypes)
    self.leftLayout.addWidget(self.project)
    
    # Add widgets to splitter
    self.splitter.addWidget(self.leftWidget)
    self.splitter.addWidget(self.details)
    
    # Set 50/50 split
    mainL = QVBoxLayout()
    mainL.setSpacing(0)
    mainL.setContentsMargins(0, 0, 0, 0)
    mainL.addWidget(self.splitter)
    self.setLayout(mainL)
    
    # Connect details resize event
    self.details.resizeEvent = self.resizeDetailsWidget  # type: ignore
    
    # Set initial splitter sizes - start with details visible in project view
    # Will be updated when view changes
    self.splitter.setSizes([1, 1])  # Start with equal sizes


  @Slot(str, str)
  def changeTable(self, docType: str = '', projectID: str = '') -> None:
    """
    What happens when user clicks to change doc-type
    -> show table
    """
    self.isProjectView = False
    self.project.hide()
    self.docTypes.show()
    # Hide details in table view if no item is selected
    if not hasattr(self.details, 'docID') or not self.details.docID or self.details.docID == '':
      self.details.hide()
      self.updateSplitterSizes(showDetails=False)
    return


  @Slot(str, str)
  def changeProject(self, projID: str = '', item: str = '') -> None:
    """
    What happens when user clicks to change project
    """
    self.isProjectView = True
    self.docTypes.hide()
    self.project.show()
    # Always show details panel in project view with 50/50 split
    self.details.show()
    self.updateSplitterSizes(showDetails=True)
    return
  
  @Slot(str)
  def changeDetails(self, docID: str) -> None:
    """
    What happens when details should be shown/hidden
    
    Args:
      docID (str): document ID, empty string to hide
    """
    if docID and docID != '' and docID != 'redraw':
      self.details.show()
      # Set splitter to 50/50
      self.updateSplitterSizes(showDetails=True)
    elif docID == '':
      # In project view, always keep details panel visible at 50/50
      if self.isProjectView:
        self.details.show()
        self.updateSplitterSizes(showDetails=True)
      else:
        # In table view, hide details when nothing is selected
        self.details.hide()
        self.updateSplitterSizes(showDetails=False)
    return
  
  def updateSplitterSizes(self, showDetails: bool = True) -> None:
    """
    Update splitter sizes to maintain 50/50 split when details are shown
    
    Args:
      showDetails (bool): Whether details should be shown
    """
    totalWidth = self.splitter.width()
    if totalWidth > 0:
      if showDetails:
        self.splitter.setSizes([totalWidth // 2, totalWidth // 2])
      else:
        self.splitter.setSizes([totalWidth, 0])
  
  def resizeEvent(self, event: Any) -> None:
    """Handle window resize to maintain 50/50 split"""
    super().resizeEvent(event)
    if self.details.isVisible():
      self.updateSplitterSizes(showDetails=True)
  
  def resizeDetailsWidget(self, _: Any) -> None:
    """ Called when details widget is resized """
    self.details.resizeWidth(self.details.width())
    return
