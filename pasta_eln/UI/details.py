""" widget that shows the details of the items """
import copy
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any
import pandas as pd
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QComboBox, QFileDialog, QLabel, QLayout, QLineEdit, QScrollArea, QTextEdit
from ..backendWorker.worker import Task
from ..fixedStringsJson import SORTED_DB_KEYS, cssStyleHtmlEditors, defaultDataHierarchyNode
from ..miscTools import isDocID
from ..textTools.handleDictionaries import dict2ul
from ..textTools.stringChanges import markdownEqualizer, tuple2html
from ._contextMenu import CommandMenu, executeContextMenu, initContextMenu
from .guiCommunicate import Communicate
from .guiStyle import IconButton, Image, Label, TextButton, widgetAndLayout
from .messageDialog import showMessage


class Details(QScrollArea):
  """ widget that shows the details of the items """
  def __init__(self, comm:Communicate):
    super().__init__()
    self.comm = comm
    self.comm.changeDetails.connect(self.change)
    self.comm.backendThread.worker.beSendDoc.connect(self.onGetData)
    self.comm.backendThread.worker.beSendTable.connect(self.onGetTable)
    self.comm.testExtractor.connect(self.testExtractor)
    self.comm.backendThread.worker.beSendTaskReport.connect(self.onTaskReport)
    self.pendingFileAdd: dict[str, Any] = {}  # Store pending file addition info
    self.doc:dict[str,Any]  = {}
    self.docID= ''
    self.idsTypesNames = pd.DataFrame(columns=['id','type','name'])
    self.textEditors:list[QTextEdit] = []
    self.editMode = False
    self.editableWidgets:dict[str, Any] = {}  # Store editable widgets by field key

    # GUI elements
    self.mainW, self.mainL = widgetAndLayout('V', None)
    self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.setWidgetResizable(True)
    self.setWidget(self.mainW)
    
    # Apply modern styling to the main widget
    bgColor = self.comm.palette.get('background', 'background-color')
    self.mainW.setStyleSheet(f"""
      QWidget {{
        {bgColor}
      }}
    """)

    headerW, self.headerL = widgetAndLayout('H', self.mainL, spacing='m', top='m', right='m', bottom='m', left='m')
    headerW.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    headerW.customContextMenuRequested.connect(lambda pos: initContextMenu(self, pos))
    # Style the header with a subtle background
    headerBg = self.comm.palette.get('secondaryDark', 'background-color')
    headerW.setStyleSheet(f"""
      QWidget {{
        {headerBg}
        border-radius: 8px;
        padding: 8px;
      }}
    """)
    self.labelW = Label('','h1', self.headerL)
    self.headerL.addStretch(1)
    self.btnEdit = IconButton('mdi.pencil', self, [Command.EDIT], self.headerL, tooltip='Edit item', checkable=True)
    IconButton('mdi.file-plus', self, [Command.ADD_FILE], self.headerL, tooltip='Add file to this item')
    IconButton('mdi.file-tree-outline', self, [Command.TO_PROJECT], self.headerL, tooltip='Change to project')
    IconButton('fa5s.times-circle',     self, [Command.CLOSE],      self.headerL, tooltip='Close')
    self.specialW, self.specialL = widgetAndLayout('V', self.mainL, top='s')
    self.specialW.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    self.specialW.customContextMenuRequested.connect(lambda pos: initContextMenu(self, pos))
    self.btnDetails = TextButton('Details', self, [Command.SHOW, 'Details'], self.mainL, \
                                 'Show / hide details', checkable=True, style='margin-top: 10px; font-weight: bold;')
    self.metaDetailsW, self.metaDetailsL  = widgetAndLayout('V', self.mainL, top='s', left='m', right='m', bottom='s')
    # Style the details section
    sectionBg = self.comm.palette.get('secondaryDark', 'background-color')
    self.metaDetailsW.setStyleSheet(f"""
      QWidget {{
        {sectionBg}
        border-radius: 6px;
        padding: 10px;
        margin: 5px;
      }}
    """)
    self.btnVendor = TextButton('Vendor metadata', self, [Command.SHOW, 'Vendor'], self.mainL, \
                                'Show / hide vendor metadata', checkable=True, style='margin-top: 15px; font-weight: bold;')
    self.metaVendorW, self.metaVendorL = widgetAndLayout('V', self.mainL, top='s', left='m', right='m', bottom='s')
    self.metaVendorW.setStyleSheet(f"""
      QWidget {{
        {sectionBg}
        border-radius: 6px;
        padding: 10px;
        margin: 5px;
      }}
    """)
    self.btnUser = TextButton('User metadata', self, [Command.SHOW, 'User'], self.mainL, \
                              'Show / hide user metadata', checkable=True, style='margin-top: 15px; font-weight: bold;')
    self.metaUserW, self.metaUserL     = widgetAndLayout('V', self.mainL, top='s', left='m', right='m', bottom='s')
    self.metaUserW.setStyleSheet(f"""
      QWidget {{
        {sectionBg}
        border-radius: 6px;
        padding: 10px;
        margin: 5px;
      }}
    """)
    # Save button for edit mode - positioned above ELN details
    self.saveButtonW, self.saveButtonL = widgetAndLayout('H', self.mainL, top='m')
    self.saveButtonL.addStretch(1)
    self.btnSave = TextButton('Save changes', self, [Command.SAVE], self.saveButtonL, 'Save all changes')
    self.btnSave.hide()
    self.btnDatabase = TextButton('ELN details', self, [Command.SHOW,'Database'], self.mainL, \
                                  'Show / hide database details', checkable= True, style='margin-top: 15px; font-weight: bold;')
    self.metaDatabaseW, self.metaDatabaseL = widgetAndLayout('V', self.mainL, top='s', left='m', right='m', bottom='s')
    self.metaDatabaseW.setStyleSheet(f"""
      QWidget {{
        {sectionBg}
        border-radius: 6px;
        padding: 10px;
        margin: 5px;
      }}
    """)
    self.mainL.addStretch(1)


  @Slot(str)
  def change(self, docID:str) -> None:
    """ What happens when user clicks to change to a different document
    Args:
      docID (str): document-id
    """
    if docID:
      self.docID = docID
      self.comm.uiRequestDoc.emit(self.docID)
    else:
      self.hide()


  @Slot(dict)
  def onGetData(self, doc:dict[str,Any]) -> None:
    """ Function to handle the received data
    Args:
      doc (dict): dictionary containing the document data
    """
    if 'id' in doc and doc['id'] == self.docID:
      self.doc = doc
      self.paint()
    elif self.pendingFileAdd and 'waitingForParent' in self.pendingFileAdd:
      # This is the parent document - update the measurement's branch path
      parentID = self.pendingFileAdd.get('parentID')
      if doc.get('id') == parentID and 'branch' in doc and doc['branch']:
        parentPath = doc['branch'][0].get('path', '')
        if parentPath:
          sourcePath = self.pendingFileAdd.get('sourcePath')
          measurementID = self.pendingFileAdd.get('measurementID')
          
          if sourcePath and measurementID:
            # Construct new path: parentPath/fileName
            newPath = f"{parentPath}/{sourcePath.name}"
            
            # Get the current measurement document to update it
            # Request it first, then update in the next onGetData call
            self.pendingFileAdd['newPath'] = newPath
            self.pendingFileAdd['parentPath'] = parentPath
            del self.pendingFileAdd['waitingForParent']
            self.comm.uiRequestDoc.emit(measurementID)
    elif self.pendingFileAdd and 'newPath' in self.pendingFileAdd:
      # This is the measurement document - update its branch path
      measurementID = self.pendingFileAdd.get('measurementID')
      if doc.get('id') == measurementID:
        newPath = self.pendingFileAdd.get('newPath')
        if newPath:
          # Update the measurement's branch path
          updatedDoc = copy.deepcopy(doc)
          if 'branch' in updatedDoc and updatedDoc['branch']:
            updatedDoc['branch'][0]['path'] = newPath
            
            # Update the document
            self.comm.uiRequestTask.emit(Task.EDIT_DOC, {'doc': updatedDoc})
            
            # Clear pending info
            self.pendingFileAdd = {}
            
            # Refresh the details after a short delay to allow update to complete
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, lambda: self.comm.changeDetails.emit(self.docID))


  @Slot(pd.DataFrame, str)
  def onGetTable(self, data:pd.DataFrame, docType:str) -> None:
    """
    Callback function to handle the received data

    Args:
      data (pd.DataFrame): DataFrame containing table
      docType (str): document type
    """
    data = data[['id','name']]
    data['type']= docType
    for _, row in data.iterrows():
      id_ = row['id']
      if id_ in self.idsTypesNames['id'].values:                            # Replace the row with matching id
        self.idsTypesNames.loc[self.idsTypesNames['id']==id_, ['name','type']] = row[['name', 'type']].values
      else:                                                                              # Concatenate new row
        self.idsTypesNames = pd.concat([self.idsTypesNames, pd.DataFrame([row])], ignore_index=True)
    
    # Update comboboxes that use this docType (in edit mode)
    if self.editMode and self.docID and 'type' in self.doc:
      # Find comboboxes that need this docType and populate them
      if self.doc['type'][0] not in self.comm.docTypesTitles:
        dataHierarchyNode = defaultDataHierarchyNode
      else:
        dataHierarchyNode = self.comm.dataHierarchyNodes[self.doc['type'][0]]
      
      for key, widget in list(self.editableWidgets.items()):  # Use list() to avoid modification during iteration
        if isinstance(widget, QComboBox):
          # Find the field that uses this docType
          fieldName = key.split('.')[-1] if '.' in key else key
          groupPrefix = key.rsplit('.', 1)[0] if '.' in key else ''
          
          matchingItems = [i for i in dataHierarchyNode 
                          if i['name'] == fieldName and 
                          i.get('list') == docType and
                          ((groupPrefix and i.get('class') == groupPrefix) or 
                           (not groupPrefix and (not i.get('class') or i.get('class') == '')))]
          
          if matchingItems:
            # This combobox uses this docType - populate it
            currentData = widget.currentData()
            widget.clear()
            widget.addItem('- no link -', '')
            for _, row in data.iterrows():
              widget.addItem(row['name'], row['id'])
            # Restore selection if possible
            if currentData:
              index = widget.findData(currentData)
              if index >= 0:
                widget.setCurrentIndex(index)
              else:
                widget.setCurrentText('- no link -')
            else:
              # Try to restore by finding the value from the document
              if groupPrefix:
                docValue = self.doc.get(groupPrefix, {}).get(fieldName, '')
              else:
                docValue = self.doc.get(fieldName, '')
              
              if isinstance(docValue, (list, tuple)) and len(docValue) > 0:
                docID = docValue[0] if isinstance(docValue[0], str) else str(docValue[0])
              elif isinstance(docValue, str):
                docID = docValue
              else:
                docID = ''
              
              if docID and re.match(r'^[a-z\-]-[a-z0-9]{32}$', docID):
                index = widget.findData(docID)
                if index >= 0:
                  widget.setCurrentIndex(index)
                else:
                  widget.setCurrentText('- no link -')
              else:
                widget.setCurrentText('- no link -')
    
    # In non-edit mode, repaint to update displayed names when table data arrives
    if not self.editMode:
      self.paint()


  @Slot()
  def paint(self) -> None:
    """ What happens when details should change """
    if self.isHidden():
      return
    # Delete old widgets from layout
    for i in reversed(range(self.metaDetailsL.count())):
      self.metaDetailsL.itemAt(i).widget().setParent(None)
    for i in reversed(range(self.metaVendorL.count())):
      self.metaVendorL.itemAt(i).widget().setParent(None)
    for i in reversed(range(self.metaUserL.count())):
      self.metaUserL.itemAt(i).widget().setParent(None)
    for i in reversed(range(self.metaDatabaseL.count())):
      self.metaDatabaseL.itemAt(i).widget().setParent(None)
    for i in reversed(range(self.specialL.count())):
      self.specialL.itemAt(i).widget().setParent(None)
    self.specialW.hide()
    self.metaDetailsW.hide()
    self.metaVendorW.hide()
    self.metaUserW.hide()
    self.metaDatabaseW.hide()
    self.btnDetails.setChecked(True)
    self.btnVendor.setChecked(True)
    self.btnUser.setChecked(True)
    self.btnDatabase.setChecked(False)
    self.textEditors = []
    self.editableWidgets = {}
    # Create new
    if not self.docID or not self.doc:
      # Don't hide - just show empty state (in project view, we want to keep the panel visible)
      self.labelW.setText('No item selected')
      return
    if self.doc['type'][0] not in self.comm.docTypesTitles:
      dataHierarchyNode = defaultDataHierarchyNode
    else:
      dataHierarchyNode = self.comm.dataHierarchyNodes[self.doc['type'][0]]
    if not self.editMode:
      self.labelW.setText(self.doc['name'] if len(self.doc['name'])<80 else self.doc['name'][:77]+'...')
      self.btnSave.hide()
      if hasattr(self, 'btnEdit'):
        self.btnEdit.setChecked(False)
    else:
      self.labelW.setText('Edit mode')
      self.btnSave.show()
      if hasattr(self, 'btnEdit'):
        self.btnEdit.setChecked(True)
    # Show image and content if present
    if 'image' in self.doc:
      Image(self.doc['image'], self.specialL, anyDimension=self.width()-20)
      self.specialW.show()
    if 'content' in self.doc:
      text = QTextEdit()                                                   # pylint: disable=qt-local-widget
      if self.editMode:
        text.setPlainText(self.doc.get('content', ''))
        text.setReadOnly(False)
        self.editableWidgets['content'] = text
      else:
        text.setMarkdown(self.doc['content'])
        text.setReadOnly(True)
      size = self.comm.configuration['GUI']['imageSizeDetails'] if hasattr(self.comm, 'configuration') else 300
      text.setFixedHeight(int(size/3*2))
      self.textEditors.append(text)
      self.specialL.addWidget(text)
      self.specialW.show()
    
    # In edit mode, show all fields from dataHierarchyNode (like the form does)
    if self.editMode:
      # Group fields by class
      groups = {i['class'] for i in dataHierarchyNode}.difference({'metaVendor','metaUser'})
      
      # Show name field
      nameW, nameL = widgetAndLayout('H', self.metaDetailsL, top='s', bottom='s')
      nameL.addWidget(QLabel('<b>Name</b>: '))
      nameEdit = QLineEdit(self.doc.get('name', ''))
      nameEdit.setValidator(QRegularExpressionValidator('[\\w\\ .-]+'))
      nameL.addWidget(nameEdit, stretch=1)
      self.editableWidgets['name'] = nameEdit
      self.metaDetailsW.show()
      
      # Show tags field
      if any(i['name'] == 'tags' for i in dataHierarchyNode):
        tagW, tagL = widgetAndLayout('H', self.metaDetailsL, top='s', bottom='s')
        tagL.addWidget(QLabel('<b>Tags</b>: '))
        tags = self.doc.get('tags', [])
        tagsList = [t for t in tags if not re.match(r'^_\d$', t)]  # Exclude rating tags
        tagStr = ' '.join(tagsList)
        tagEdit = QLineEdit(tagStr)
        tagL.addWidget(tagEdit, stretch=1)
        self.editableWidgets['tags'] = tagEdit
      
      # Show all fields from dataHierarchyNode
      for group in groups:
        for item in dataHierarchyNode:
          if item['class'] == group:
            name = item['name']
            key = f"{group}.{name}" if group else f".{name}"
            
            # Skip special fields handled separately
            if name in ['name', 'tags', 'comment', 'content']:
              if name == 'comment':
                # Handle comment
                commentW, commentL = widgetAndLayout('H', self.metaDetailsL, top='s', bottom='s')
                commentL.addWidget(QLabel('<b>Comment</b>: '), alignment=Qt.AlignmentFlag.AlignTop)
                commentEdit = QTextEdit()
                commentEdit.setPlainText(self.doc.get('comment', ''))
                commentEdit.setReadOnly(False)
                commentEdit.setFixedHeight(100)
                commentL.addWidget(commentEdit, stretch=1)
                self.editableWidgets['comment'] = commentEdit
              continue
            
            # Get value from doc
            if group:
              value = self.doc.get(group, {}).get(name, '')
            else:
              # For top-level fields, check both with and without dot prefix
              # Reference fields are stored with dot prefix (e.g., '.workflow/procedure')
              value = self.doc.get(f'.{name}', self.doc.get(name, ''))
            
            # Skip if empty and not in doc (but show in edit mode)
            if not value and name not in self.doc and group and name not in self.doc.get(group, {}):
              value = ''  # Show empty field in edit mode
            
            # Show the field
            if group:
              # Nested field - add to appropriate group layout
              if group not in ['metaVendor', 'metaUser']:
                self.addDocDetails(self.metaDetailsL, name, value, dataHierarchyNode, groupPrefix=group)
            else:
              # Top-level field
              if name not in SORTED_DB_KEYS and name not in ['name', 'tags', 'comment', 'content', 'image']:
                self.addDocDetails(self.metaDetailsL, name, value, dataHierarchyNode, groupPrefix='')
      
      self.metaDetailsW.show()
      
      # Handle metaVendor and metaUser
      if any(i['class'] == 'metaVendor' for i in dataHierarchyNode):
        self.btnVendor.show()
        metaVendor = self.doc.get('metaVendor', {})
        self.addDocDetails(self.metaVendorL, '', metaVendor, dataHierarchyNode, groupPrefix='metaVendor')
        self.metaVendorW.show()
      if any(i['class'] == 'metaUser' for i in dataHierarchyNode):
        self.btnUser.show()
        metaUser = self.doc.get('metaUser', {})
        self.addDocDetails(self.metaUserL, '', metaUser, dataHierarchyNode, groupPrefix='metaUser')
        self.metaUserW.show()
      
      # Show database keys
      for key in SORTED_DB_KEYS:
        if key in self.doc and key not in ['id', 'type', 'branch']:
          self.addDocDetails(self.metaDatabaseL, key, self.doc[key], dataHierarchyNode, groupPrefix='')
          self.btnDatabase.setChecked(False)
    else:
      # Non-edit mode: show all fields from dataHierarchyNode (like edit mode, but read-only)
      # Group fields by class
      groups = {i['class'] for i in dataHierarchyNode}.difference({'metaVendor','metaUser'})
      
      # Show tags (always show, even if empty)
      tags = self.doc.get('tags', [])
      if tags or any(i['name'] == 'tags' for i in dataHierarchyNode):
        self.addDocDetails(self.metaDetailsL, 'tags', tags, dataHierarchyNode, groupPrefix='')
      
      # Show comment (always show, even if empty)
      comment = self.doc.get('comment', '')
      if comment or any(i['name'] == 'comment' for i in dataHierarchyNode):
        self.addDocDetails(self.metaDetailsL, 'comment', comment, dataHierarchyNode, groupPrefix='')
      
      # Show all fields from dataHierarchyNode
      for group in groups:
        for item in dataHierarchyNode:
          if item['class'] == group:
            name = item['name']
            key = f"{group}.{name}" if group else f".{name}"
            
            # Skip special fields handled separately
            if name in ['name', 'tags', 'comment', 'content']:
              continue
            
            # Get value from doc - handle dot notation (fields starting with . are top-level)
            if group:
              # Nested field
              value = self.doc.get(group, {}).get(name, '')
            else:
              # Top-level field - use same logic as form.py line 316-317
              # Form does: self.doc.get(group, {}).get(row.name, ('','','',''))
              # where group is '' for top-level fields
              # The hierarchy() function converts flat keys like '.workflow/procedure' 
              # into nested structure: {'': {'workflow/procedure': value}}
              groupDict = self.doc.get('', {})
              if isinstance(groupDict, dict):
                defaultValue = groupDict.get(name, None)
                # Handle tuple values (value, unit, label, PURL) - extract just the value
                if isinstance(defaultValue, tuple) and len(defaultValue) >= 1:
                  value = defaultValue[0]
                elif defaultValue is not None:
                  value = defaultValue
                else:
                  value = None
              else:
                value = None
              
              # If not found in nested structure, try dot-prefixed key directly (fallback)
              if value is None:
                dotKey = f'.{name.lstrip(".")}'
                defaultValue = self.doc.get(dotKey, None)
                if isinstance(defaultValue, tuple) and len(defaultValue) >= 1:
                  value = defaultValue[0]
                elif defaultValue is not None:
                  value = defaultValue
                else:
                  value = ''
              
              # Default to empty string if not found
              if value is None:
                value = ''
              
              # Debug logging for reference fields
              if name in ['workflow/procedure', 'sample', 'device'] or '/' in name:
                allKeys = list(self.doc.keys())
                dotKeys = [k for k in allKeys if k.startswith(".")]
                hasEmptyGroup = '' in self.doc and isinstance(self.doc[''], dict)
                logging.debug(f'Reading field {name}: value={repr(value)}, type={type(value)}, has_empty_group={hasEmptyGroup}, empty_group_keys={list(self.doc.get("", {}).keys())[:5] if hasEmptyGroup else []}, dotKeys={dotKeys[:10]}')
            
            # Always show fields from data hierarchy (even if empty, to show "- no link -" for list fields)
            if group:
              # Nested field - add to appropriate group layout
              if group not in ['metaVendor', 'metaUser']:
                self.addDocDetails(self.metaDetailsL, name, value, dataHierarchyNode, groupPrefix=group)
            else:
              # Top-level field
              if name not in SORTED_DB_KEYS and name not in ['name', 'tags', 'comment', 'content', 'image']:
                # Pass the name as-is (without dot) - addDocDetails will handle matching
                # The value should already be read correctly with dot prefix check above
                self.addDocDetails(self.metaDetailsL, name, value, dataHierarchyNode, groupPrefix='')
      
      # Always show metaDetailsW if we have any fields
      if self.metaDetailsL.count() > 0:
        self.metaDetailsW.show()
      else:
        self.metaDetailsW.hide()
      
      # Handle metaVendor and metaUser
      if 'metaVendor' in self.doc:
        self.btnVendor.show()
        self.addDocDetails(self.metaVendorL, '', self.doc['metaVendor'], dataHierarchyNode, groupPrefix='metaVendor')
        self.metaVendorW.show()
      else:
        self.btnVendor.hide()
      
      if 'metaUser' in self.doc:
        self.btnUser.show()
        self.addDocDetails(self.metaUserL, '', self.doc['metaUser'], dataHierarchyNode, groupPrefix='metaUser')
        self.metaUserW.show()
      else:
        self.btnUser.hide()
      
      # Show database keys
      for key in SORTED_DB_KEYS:
        if key in self.doc and key not in ['id', 'type', 'branch']:
          self.addDocDetails(self.metaDatabaseL, key, self.doc[key], dataHierarchyNode, groupPrefix='')
          self.btnDatabase.setChecked(False)
    return


  def execute(self, command:list[Any]) -> None:
    """
    Hide / show the widget underneath the button

    Args:
      command (list): area to show/hide
    """
    if command[0] is Command.SHOW:
      if getattr(self, f'btn{command[1]}').isChecked():                                #get button in question
        getattr(self, f'meta{command[1]}W').show()
      else:
        getattr(self, f'meta{command[1]}W').hide()
    elif command[0] is Command.CLOSE:
      self.hide()
    elif command[0] is Command.EDIT:
      # Toggle edit mode
      if self.docID:
        self.editMode = not self.editMode
        self.paint()  # Repaint with edit mode
    elif command[0] is Command.SAVE:
      # Save changes
      if self.docID and self.editMode:
        self.saveChanges()
    elif command[0] is Command.ADD_FILE:
      # Add file to this document
      if self.docID and 'branch' in self.doc and len(self.doc['branch']) > 0:
        self.addFileToDocument()
    elif command[0] is Command.TO_PROJECT:
      self.comm.changeProject.emit(self.doc['branch'][0]['stack'][0], self.doc['id'])
    elif isinstance(command[0], CommandMenu):
      if executeContextMenu(self, command):
        self.comm.changeTable.emit('','')
        self.comm.changeDetails.emit(self.doc['id'])
    else:
      logging.error('Details command unknown: %s',command, exc_info=True)
    return


  @Slot()
  def testExtractor(self) -> None:
    """
    User selects to test extractor on this dataset
    """
    logging.debug('details:testExtractor')
    if len(self.doc)>1:
      pathStr = self.doc['branch'][0]['path']
      if pathStr is None:
        showMessage(self, 'Warning', 'Selected item has no path.')
      else:
        path = Path(pathStr)
        if not path.as_posix().startswith('http'):
          path = self.comm.basePath/path
        self.comm.uiRequestTask.emit(Task.EXTRACTOR_TEST, {'fileName':str(path), 'style':'html', 'recipe':'', 'saveFig':''})
    else:
      showMessage(self, 'Warning', 'No item was selected via list-view, i.e. no details are shown.')
    return


  def resizeWidth(self, width:int) -> None:
    """ called if details is resized by splitter at the parent widget
    - resize all text-documents
    """
    if not self.textEditors:
      return
    self.metaDetailsW.setFixedWidth(width)
    for text in self.textEditors:
      text.document().setTextWidth(width-80)
      height:int = text.document().size().toTuple()[1]                                    # type:ignore[index]
      text.setFixedHeight(height)
    return



  def addDocDetails(self, layout:QLayout, key:str, value:Any, dataHierarchyNode:list[dict[str,Any]], groupPrefix:str='') -> str:
    """ add document details to a widget's layout: take care of all the formatting

    Args:
      layout (QLayout): layout to which to add
      key    (str): key/label to add
      value  (Any): information
      dataHierarchyNode (list): information on data-structure
      groupPrefix (str): prefix for nested groups (e.g., 'metaVendor')

    Returns:
      str: /n separated lines of text
    """
    if not key and isinstance(value,dict):
      return '\n'.join([self.addDocDetails(layout, k, v, dataHierarchyNode, groupPrefix) for k, v in value.items()])
    # In non-edit mode, show all fields even if empty - display "N/A" for empty values
    # BUT: Don't modify value if it's a list field - let the list field handling below deal with it
    isListField = False
    if not self.editMode:
      # Check if this is a list field - if so, we'll handle it below
      # Match by key name, handling dot-prefixed keys
      keyName = key.lstrip('.')
      dataHierarchyItems = [dict(i) for i in dataHierarchyNode if i['name']==keyName or i['name']==key]
      if dataHierarchyItems and dataHierarchyItems[0].get('list'):
        isListField = True
      elif not value:
        # Not a list field and empty - show "N/A" instead of skipping
        value = 'N/A'
    link = False
    labelStr = ''
    if key=='tags':
      if self.editMode and layout is not None:
        # Editable tags - simple text input for now
        tagW, tagL = widgetAndLayout('H', layout, top='s', bottom='s')
        tagL.addWidget(QLabel('<b>Tags</b>: '))
        rating = ['\u2605'*int(i[1]) for i in value if re.match(r'^_\d$', i)]
        tags = [i for i in value if not re.match(r'^_\d$', i)]
        tagStr = ' '.join(tags)
        tagEdit = QLineEdit(tagStr)
        tagL.addWidget(tagEdit, stretch=1)
        self.editableWidgets['tags'] = tagEdit
        labelStr = f'Rating: {rating[0]}' if rating else ''
        labelStr = f'{labelStr}   Tags: {tagStr}'
      else:
        rating = ['\u2605'*int(i[1]) for i in value if re.match(r'^_\d$', i)]
        tags = [i for i in value if not re.match(r'^_\d$', i)]
        # Format tags with bold label like other fields
        ratingStr = f'Rating: {rating[0]}' if rating else ''
        tagsStr = ' '.join(tags) if tags else 'N/A'
        labelStr = f'<b>Tags</b>: {ratingStr + "   " if ratingStr else ""}{tagsStr}'
        if layout is not None:
          label = QLabel(labelStr)
          label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
          # Style the label for better readability
          label.setStyleSheet("""
            QLabel {
              padding: 6px 8px;
              border-radius: 4px;
              margin: 2px 0px;
            }
            QLabel:hover {
              background-color: rgba(128, 128, 128, 30);
            }
          """)
          layout.addWidget(label)
    elif (isinstance(value,str) and '\n' in value) or key=='comment':        # long values with /s or comments
      labelW, labelL = widgetAndLayout('H', layout, top='s', bottom='s')
      # Use bold label like other fields for consistency
      labelL.addWidget(QLabel(f'<b>{key.capitalize()}</b>: '), alignment=Qt.AlignmentFlag.AlignTop)
      
      # For "N/A" values, use a simple label instead of QTextEdit for better visibility
      if not self.editMode and value == 'N/A':
        naLabel = QLabel('N/A')
        naLabel.setStyleSheet("""
          QLabel {
            padding: 8px 12px;
            border-radius: 4px;
            background-color: rgba(128, 128, 128, 50);
            color: rgba(100, 100, 100, 255);
            font-size: 13px;
            min-height: 30px;
          }
        """)
        labelL.addWidget(naLabel, stretch=1)
      else:
        text = QTextEdit()                                                     # pylint: disable=qt-local-widget
        if self.editMode:
          # In edit mode, use actual value (not "N/A")
          displayValue = value if value != 'N/A' else ''
          text.setPlainText(displayValue)  # Use plain text for editing
          text.setReadOnly(False)
          self.editableWidgets[key] = text
        else:
          # In non-edit mode, show markdown
          text.setMarkdown(markdownEqualizer(value))
          text.setReadOnly(True)
        bgColor = self.comm.palette.get('secondaryDark', 'background-color')
        fgColor = self.comm.palette.get('secondaryText', 'color')
        text.setStyleSheet(f"QTextEdit {{ border: {'1px solid #888' if self.editMode else 'none'}; padding: 3px; {bgColor} {fgColor}}}")
        try:                                    #Temporary debugging until June26 to identify the cause of issue
          text.document().setTextWidth(labelW.width())
        except Exception:
          logging.error('text.document is something erroneous: %s, %s', type(text), type(text.document()))
        if hasattr(self, 'rescaleTexts'):
          self.textEditors.append(text)
        height:int = text.document().size().toTuple()[1]                                    # type:ignore[index]
        # Set minimum height to ensure readability
        minHeight = 40 if height < 40 else height
        text.setFixedHeight(minHeight)
        self.textEditors.append(text)
        labelL.addWidget(text, stretch=1)
    else:
      # Match by key name, handling dot-prefixed keys
      # The key might be 'workflow/procedure' but dataHierarchyNode has 'workflow/procedure' (no dot)
      keyName = key.lstrip('.')
      dataHierarchyItems = [dict(i) for i in dataHierarchyNode if i['name']==keyName or i['name']==key]
      docID = ''
      # Debug: log what we found
      if key in ['workflow/procedure', 'sample', 'device'] or '/' in key:
        logging.debug(f'addDocDetails for {key}: value={value}, type={type(value)}, dataHierarchyItems={len(dataHierarchyItems)}, value_repr={repr(value)}')
      if len(dataHierarchyItems)==1 and 'list' in dataHierarchyItems[0] and dataHierarchyItems[0]['list'] and \
          ',' not in dataHierarchyItems[0]['list'] and ' ' not  in dataHierarchyItems[0]['list']:#choice among docType
        listDocType = dataHierarchyItems[0]['list']
        
        # Handle value - it could be a string, list, tuple, or empty
        # Reference fields can be stored as string (docID) or list [docID]
        if isinstance(value, (list, tuple)) and len(value) > 0:
          docIDValue = value[0] if isinstance(value[0], str) else str(value[0])
        elif isinstance(value, str) and value:
          docIDValue = value
        else:
          docIDValue = ''
        
        # Debug logging for reference fields
        if key in ['workflow/procedure', 'sample', 'device'] or '/' in key:
          logging.debug(f'Reference field {key}: value={value}, docIDValue={docIDValue}, listDocType={listDocType}')
        
        # Check if we have the table data for this docType
        if listDocType not in self.idsTypesNames['type'].values:
          # Request the data - it will be displayed when data arrives
          self.comm.uiRequestTable.emit(listDocType, '', True)
          # For now, show the docID or a placeholder
          if docIDValue and re.match(r'^[a-z\-]-[a-z0-9]{32}$', docIDValue):
            value = f'Loading... ({docIDValue[:8]}...)'
          else:
            value = docIDValue if docIDValue else '- no link -'
        else:
          # Data is available - convert docID to name (same logic as form.py)
          if docIDValue:
            # Ensure docIDValue is a string
            docIDValue = str(docIDValue).strip()
            # Filter the dataframe - same as form.py line 227-230
            matching_rows = self.idsTypesNames[(self.idsTypesNames.id==docIDValue) & (self.idsTypesNames.type==listDocType)]
            names = list(matching_rows['name']) if not matching_rows.empty else []
            
            if len(names)==1:                                            # default find one item that we link to
              docID = docIDValue
              value = '\u260D '+names[0]  # Same format as form displays
              link = True
            elif not names:
              # docID not found in table - might be invalid or deleted
              # Show the docID itself if it's valid, otherwise show "- no link -"
              if docIDValue and re.match(r'^[a-z\-]-[a-z0-9]{32}$', docIDValue):
                value = f'Unknown ({docIDValue[:8]}...)' if len(docIDValue) > 8 else docIDValue
              else:
                value = '- no link -'
            else:
              raise ValueError(f'list target exists multiple times. Key: {key}')
          else:
            # Empty value, no link
            value = '- no link -'
      elif isinstance(value, list):
        if len(value) == 0:
          value = 'N/A'
        else:
          value = ', '.join([str(i) for i in value])
      # Handle empty string values - show as "N/A" (but not if it's already "N/A" from earlier)
      elif isinstance(value, str) and value == '':
        value = 'N/A'
      # Check for tuple with docID that cannot be resolved
      if isinstance(value, tuple) and len(value)==4:
        if isDocID(value[0]):
          value = 'Cannot resolve link'
      labelStr = f'<b>{key.capitalize()}</b>: {value}'
      if isinstance(value, tuple) and len(value)==4:
        k,v = tuple2html(key, value)
        labelStr = f'{k}: {v}<br>'
      if isinstance(value, dict):
        newValue = {}
        for k,v in value.items():
          if isinstance(v, tuple) and len(v)==4:
            k2,v2 = tuple2html(k, v)
            newValue[k2] = v2
          elif isinstance(v, (list, tuple)):
            newValue[k] = v[0]
          else:
            newValue[k] = v
        labelStr = f'{cssStyleHtmlEditors}{key}: {dict2ul(newValue)}'
      if layout is not None:
        # ELN details (SORTED_DB_KEYS) should never be editable - always show as read-only
        isELNDetail = key in SORTED_DB_KEYS
        if self.editMode and not link and not isELNDetail and key not in ['id', 'type', 'branch'] and not isinstance(value, (dict, tuple)) and len(str(value)) < 200:
          # Make editable for simple fields (skip dicts, tuples, and very long values)
          fieldW, fieldL = widgetAndLayout('H', layout, top='s', bottom='s')
          fieldL.addWidget(QLabel(f'<b>{key.capitalize()}</b>: '))
          
          # Check if this field has a list (dropdown) in dataHierarchyNode
          # Match by name and class/groupPrefix
          dataHierarchyItem = [i for i in dataHierarchyNode 
                              if i['name']==key and 
                              ((groupPrefix and i.get('class')==groupPrefix) or 
                               (not groupPrefix and (not i.get('class') or i.get('class')=='')))]
          if dataHierarchyItem and dataHierarchyItem[0].get('list'):
            # This is a dropdown field
            listValue = dataHierarchyItem[0]['list']
            fieldEdit = QComboBox()
            
            # Handle tuple values (extract first element)
            if isinstance(value, tuple) and len(value) >= 1:
              displayValue = value[0]
            else:
              displayValue = str(value) if value else ''
            
            if ',' in listValue:
              # Static list from dataHierarchy (comma-separated)
              fieldEdit.addItems(listValue.split(','))
              fieldEdit.setCurrentText(displayValue)
            else:
              # Dynamic list from docType - need to request table data
              fieldEdit.addItem('- no link -', '')
              
              # Check if we already have data for this docType
              if listValue in self.idsTypesNames['type'].values:
                # Data is available - populate immediately
                for _, row in self.idsTypesNames[self.idsTypesNames.type==listValue].iterrows():
                  fieldEdit.addItem(row['name'], row['id'])
                
                # Set current value if it's a docID
                if isinstance(value, (list, tuple)) and len(value) > 0:
                  docID = value[0] if isinstance(value[0], str) else str(value[0])
                elif isinstance(value, str) and value:
                  docID = value
                else:
                  docID = ''
                
                if docID and re.match(r'^[a-z\-]-[a-z0-9]{32}$', docID):
                  # It's a docID, try to find it in the combobox
                  index = fieldEdit.findData(docID)
                  if index >= 0:
                    fieldEdit.setCurrentIndex(index)
                  else:
                    fieldEdit.setCurrentText('- no link -')
                elif displayValue and displayValue != '- no link -':
                  # Try to find by text
                  index = fieldEdit.findText(displayValue)
                  if index >= 0:
                    fieldEdit.setCurrentIndex(index)
                  else:
                    fieldEdit.setCurrentText('- no link -')
                else:
                  fieldEdit.setCurrentText('- no link -')
              else:
                # Data not available yet - request it
                self.comm.uiRequestTable.emit(listValue, '', True)
                # Set current value as text for now (will be updated when data arrives)
                if displayValue and displayValue != '- no link -':
                  fieldEdit.setCurrentText(displayValue)
                else:
                  fieldEdit.setCurrentText('- no link -')
          else:
            # Regular text field
            if isinstance(value, (list, tuple)):
              valueStr = ', '.join([str(i) for i in value])
            else:
              valueStr = str(value) if value else ''
            fieldEdit = QLineEdit(valueStr)
          
          fieldL.addWidget(fieldEdit, stretch=1)
          # Store with full path if we're in a nested context
          fullKey = f'{groupPrefix}.{key}' if groupPrefix else key
          self.editableWidgets[fullKey] = fieldEdit
        else:
          label = Label(labelStr, function=lambda x,y: self.clickLink(x,y) if link else None, docID=docID)
          label.setOpenExternalLinks(True)
          label.setWordWrap(True)
          # Style the label for better readability
          label.setStyleSheet("""
            QLabel {
              padding: 6px 8px;
              border-radius: 4px;
              margin: 2px 0px;
            }
            QLabel:hover {
              background-color: rgba(128, 128, 128, 30);
            }
          """)
          layout.addWidget(label)
    return labelStr


  def clickLink(self, label:str, docID:str) -> None:
    """
    Click link in details

    Args:
      label (str): label on link
      docID (str): docID to which to link
    """
    logging.debug('used link on %s|%s',label,docID)
    self.comm.changeDetails.emit(docID)
    return


  def addFileToDocument(self) -> None:
    """
    Add a file to the current document by selecting it via file dialog and updating the branch path
    """
    if not self.docID or 'branch' not in self.doc or not self.doc['branch']:
      showMessage(self, 'Error', 'Cannot add file: document information is missing.')
      return
    
    branch = self.doc['branch'][0]
    if not branch.get('stack'):
      showMessage(self, 'Error', 'Cannot add file: document is not in a project.')
      return
    
    # Open file dialog
    fileName, _ = QFileDialog.getOpenFileName(self, 'Select file to add to measurement', str(Path.home()), '*.*')
    if not fileName:
      return
    
    sourcePath = Path(fileName)
    if not sourcePath.exists() or not sourcePath.is_file():
      showMessage(self, 'Error', 'Selected file does not exist.')
      return
    
    # Get parent folder ID
    parentID = branch['stack'][-1] if branch['stack'] else ''
    if not parentID:
      showMessage(self, 'Error', 'Cannot determine parent folder.')
      return
    
    # Store info for after file is copied
    self.pendingFileAdd = {
      'sourcePath': sourcePath,
      'parentID': parentID,
      'measurementID': self.docID
    }
    
    # Request parent document to get its path
    self.comm.uiRequestDoc.emit(parentID)
    
    # Use DROP_EXTERNAL to copy the file to the parent folder
    self.comm.uiRequestTask.emit(Task.DROP_EXTERNAL, {
      'docID': parentID,
      'files': [str(sourcePath)],
      'folders': []
    })
    
    showMessage(self, 'Info', f'File "{sourcePath.name}" is being copied. The measurement will be updated after copying.')
    return


  @Slot(Task, str, str, str)
  def onTaskReport(self, task: Task, reportText: str, image: str, path: str) -> None:
    """
    Handle task completion reports
    
    Args:
      task (Task): The task that completed
      reportText (str): Report message
      image (str): Image data (if any)
      path (str): Path (if any)
    """
    if task == Task.DROP_EXTERNAL and self.pendingFileAdd and 'Drag-drop operation finished successfully' in reportText:
      # File copy completed, now update the measurement's branch path
      sourcePath = self.pendingFileAdd.get('sourcePath')
      measurementID = self.pendingFileAdd.get('measurementID')
      
      if sourcePath and measurementID == self.docID:
        # Request parent document to get its path, then update measurement
        parentID = self.pendingFileAdd.get('parentID')
        if parentID:
          # Store flag to update after getting parent doc
          self.pendingFileAdd['waitingForParent'] = True
          # Request parent doc (we'll handle update in onGetData)
          self.comm.uiRequestDoc.emit(parentID)
    return


  def saveChanges(self) -> None:
    """
    Collect all edited values and save them via Task.EDIT_DOC
    """
    if not self.docID or not self.doc:
      logging.warning('Cannot save: missing docID or doc')
      return
    
    if not self.editableWidgets:
      logging.warning('No editable widgets found - nothing to save')
      return
    
    # Get dataHierarchyNode to check field types
    if self.doc['type'][0] not in self.comm.docTypesTitles:
      from ..fixedStringsJson import defaultDataHierarchyNode
      dataHierarchyNode = defaultDataHierarchyNode
    else:
      dataHierarchyNode = self.comm.dataHierarchyNodes[self.doc['type'][0]]
    
    # Create updated document
    updatedDoc = copy.deepcopy(self.doc)
    
    logging.debug(f'Saving changes. Editable widgets: {list(self.editableWidgets.keys())}')
    
    # Collect values from editable widgets
    for key, widget in self.editableWidgets.items():
      if isinstance(widget, QComboBox):
        # Handle dropdown/combobox fields
        valueNew = widget.currentText()
        dataNew = widget.currentData()  # docID if stored in currentData
        
        # Check if currentData contains a valid docID
        if dataNew is not None and re.search(r'^[a-z\-]-[a-z0-9]{32}$', str(dataNew)) is not None:
          docIDValue = dataNew  # Use docID
        elif valueNew != '- no link -' and dataNew is None:
          docIDValue = valueNew  # Use text value
        else:
          docIDValue = ''  # Empty selection
        
        # Get original value to determine structure
        if '.' in key:
          group, field = key.split('.', 1)
          if group not in updatedDoc:
            updatedDoc[group] = {}
          origValue = updatedDoc[group].get(field, '')
        else:
          origValue = updatedDoc.get(key, '')
        
        # Determine if this is a reference field (list field) that should be stored as a list
        # Check dataHierarchyNode to see if this field has a 'list' property
        isReferenceField = False
        # Handle dot-prefixed keys (like '.workflow/procedure', '.sample', '.device')
        fieldName = key.lstrip('.')
        fieldItems = [item for item in dataHierarchyNode if item['name'] == fieldName or item['name'] == key]
        if fieldItems:
          fieldItem = fieldItems[0]
          if fieldItem.get('list') and fieldItem['list'] and \
             ',' not in fieldItem['list'] and ' ' not in fieldItem['list']:
            isReferenceField = True
        
        # For reference fields, they should be stored as lists [docID] in the document
        # The flatten function will enumerate lists, creating keys like "0" for the first element
        # But updateDoc expects strings for properties with dots/slashes
        # So we need to store as string (docID) for fields with dots/slashes in the key
        if isReferenceField:
          # Check if key has a dot or slash (like '.workflow/procedure')
          if '.' in key or '/' in key:
            # For keys with dots/slashes, store as string (docID) to match updateDoc expectations
            value = docIDValue if docIDValue else ''
          else:
            # For other reference fields, store as list [docID]
            value = [docIDValue] if docIDValue else []
        elif isinstance(origValue, tuple) and len(origValue) == 4:
          # Preserve tuple structure: (value, unit, label, PURL)
          value = (docIDValue, origValue[1] if len(origValue) > 1 else '', 
                  origValue[2] if len(origValue) > 2 else '', 
                  origValue[3] if len(origValue) > 3 else '')
        elif isinstance(origValue, list) and not isReferenceField:
          # Preserve list structure if it was a list (but not a reference field)
          value = [docIDValue] if docIDValue else []
        else:
          value = docIDValue
        
        # Store the value
        # For reference fields that should have a dot prefix (like workflow/procedure -> .workflow/procedure)
        # Check if this is a top-level reference field that needs a dot prefix
        if isReferenceField and not key.startswith('.') and '.' not in key:
          # This is a top-level reference field (like 'workflow/procedure', 'sample', 'device')
          # It should be stored with a dot prefix ('.workflow/procedure', '.sample', '.device')
          dotKey = f'.{key}'
          updatedDoc[dotKey] = value
        elif '.' in key and not key.startswith('.'):
          # Nested field (like 'metaVendor.fieldName')
          group, field = key.split('.', 1)
          if group not in updatedDoc:
            updatedDoc[group] = {}
          updatedDoc[group][field] = value
        else:
          # Already has dot prefix or is a regular field
          updatedDoc[key] = value
      elif isinstance(widget, QLineEdit):
        value = widget.text().strip()
        if key == 'name':
          updatedDoc['name'] = value
        elif key == 'tags':
          # Parse tags from space-separated string
          tags = [tag.strip() for tag in value.split() if tag.strip()]
          # Preserve rating if it exists
          rating = [tag for tag in self.doc.get('tags', []) if re.match(r'^_\d$', tag)]
          updatedDoc['tags'] = rating + tags
        else:
          # Handle nested fields (e.g., 'metaVendor.fieldName' or 'group.fieldName')
          if '.' in key:
            group, field = key.split('.', 1)
            if group not in updatedDoc:
              updatedDoc[group] = {}
            # Get original value to preserve structure
            origValue = updatedDoc[group].get(field, '')
            if isinstance(origValue, list):
              updatedDoc[group][field] = [v.strip() for v in value.split(',') if v.strip()] if value else []
            elif isinstance(origValue, tuple):
              try:
                updatedDoc[group][field] = tuple(v.strip() for v in value.split(',')) if value else tuple()
              except:
                updatedDoc[group][field] = value
            else:
              # For new fields or simple values, store as string (empty if blank)
              updatedDoc[group][field] = value if value else ''
          else:
            # Top-level field
            origValue = updatedDoc.get(key, '')
            if isinstance(origValue, list):
              updatedDoc[key] = [v.strip() for v in value.split(',') if v.strip()] if value else []
            elif isinstance(origValue, tuple):
              try:
                updatedDoc[key] = tuple(v.strip() for v in value.split(',')) if value else tuple()
              except:
                updatedDoc[key] = value
            else:
              # For new fields or simple values, store as string (empty if blank)
              updatedDoc[key] = value if value else ''
      elif isinstance(widget, QTextEdit):
        value = widget.toPlainText().strip()
        if key == 'comment':
          updatedDoc['comment'] = value
        elif key == 'content':
          updatedDoc['content'] = value
        else:
          updatedDoc[key] = value
    
    # Ensure document ID is preserved
    if 'id' not in updatedDoc or updatedDoc['id'] != self.docID:
      updatedDoc['id'] = self.docID
    
    # Ensure document type is preserved
    if 'type' not in updatedDoc:
      updatedDoc['type'] = self.doc.get('type', [''])
    
    # Emit task to save changes
    logging.info(f'Saving changes for document {self.docID}')
    logging.debug(f'Updated document keys: {list(updatedDoc.keys())}')
    logging.debug(f'Editable widgets processed: {list(self.editableWidgets.keys())}')
    
    # Get project ID from branch if available
    newProjID = None
    if 'branch' in updatedDoc and updatedDoc['branch'] and len(updatedDoc['branch']) > 0:
      branch = updatedDoc['branch'][0]
      if 'stack' in branch and branch['stack']:
        newProjID = [branch['stack'][0]]  # Project ID is first in stack
    
    # Send the updated document to the backend
    # Backend expects both 'doc' and 'newProjID' keys
    self.comm.uiRequestTask.emit(Task.EDIT_DOC, {'doc': updatedDoc, 'newProjID': newProjID})
    
    # Exit edit mode
    self.editMode = False
    # Refresh details to show updated values (will be updated when backend responds)
    self.comm.changeDetails.emit(self.docID)
    return


class Command(Enum):
  """ Commands used in this file """
  SHOW             = 1
  CLOSE            = 2
  TO_PROJECT       = 3
  EDIT             = 4
  SAVE             = 5
  ADD_FILE         = 6
