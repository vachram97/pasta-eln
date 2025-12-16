""" widget that shows the table of the items """
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget
from .guiCommunicate import Communicate
from .table import Table


class DocTypes(QWidget):
  """ widget that shows the table of the items """
  def __init__(self, comm:Communicate):
    super().__init__()
    comm.changeTable.connect(self.changeTable)
    # GUI elements - details panel is now handled by Body widget
    table = Table(comm)
    mainL = QVBoxLayout()
    mainL.setSpacing(0)
    mainL.setContentsMargins(0, 0, 0, 0)
    mainL.addWidget(table)
    self.setLayout(mainL)


  @Slot(str, str)
  def changeTable(self, docType: str = '', projectID: str = '') -> None:
    """What happens when user clicks to change doc-type -> show table """
    return
