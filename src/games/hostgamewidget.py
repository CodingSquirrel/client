#-------------------------------------------------------------------------------
# Copyright (c) 2012 Gael Honorez.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#-------------------------------------------------------------------------------

import logging

from PyQt5.QtCore import *
from PyQt5.QtNetwork import *

from games.gameitem import GameItem, GameItemDelegate
import modvault
from fa import maps
from fa.mod import Mod
from fa.game_version import GameVersion
from git.version import Version
import util
from client import RES
from faftools.api.VersionService import VersionService

logger = logging.getLogger(__name__)

RANKED_SEARCH_EXPANSION_TIME = 10000 #milliseconds before search radius expands

SEARCH_RADIUS_INCREMENT = 0.05
SEARCH_RADIUS_MAX = 0.25

FormClass, BaseClass = util.loadUiType("games/host.ui")


class HostgameWidget(FormClass, BaseClass):
    def __init__(self, parent, main_mod='faf', allow_map_choice=True):
        BaseClass.__init__(self)

        logger.debug("HostGameWidget started with: %s, %s", main_mod, allow_map_choice)

        self.setupUi(self)
        self.parent = parent
        self.client = parent.client
        
        self.parent.options = []

        self.setStyleSheet(self.parent.client.styleSheet())
        
        self.setWindowTitle("Host Game: " + main_mod)
        self.titleEdit.setText(self.parent.gamename)
        self.passEdit.setText(self.parent.gamepassword)
        self.game = GameItem(0)
        self.gamePreview.setItemDelegate(GameItemDelegate(self))
        self.gamePreview.addItem(self.game)

        self.map = ''

        nickname = self.parent.client.login

        self.message = {}
        self.message['Title'] = self.parent.gamename
        self.message['Host'] = {'username':self.parent.client.login}
        self.message['teams'] = {1:[self.parent.client.login]}
#        self.message.get('access', 'public')
        self.message['featured_mod'] = "faf"
        self.message['mapname'] = self.parent.gamemap
        self.message['GameState'] = "Lobby"
        self.message["GameOption"] = {"Slots": 12}

        msg = self.message

        msg["PlayerOption"] = {}
        msg["PlayerOption"][1] = {"PlayerName": nickname,
                                  "Team": 1}
        self.game.update(self.message, self.parent.client)

        self.versions = []
        self.selectedVersion = 0
        self.versionList.setVisible(False)
        self.gameVersionLabel.setVisible(False)

        self.switch_main_mod(main_mod)
        i = 0
        index = 0
        if allow_map_choice:
            allmaps = dict()
            for map in list(maps.maps.keys()) + maps.getUserMaps():
                allmaps[map] = maps.getDisplayName(map)
            for (map, name) in sorted(iter(allmaps.items()), key=lambda x: x[1]):
                if map == self.parent.gamemap:
                    index = i
                self.mapList.addItem(name, map)
                i = i + 1
            self.mapList.setCurrentIndex(index)
        else:
            self.mapList.hide()
            
        icon = maps.preview(self.parent.gamemap, True)

        if not icon:
            icon = util.icon("games/unknown_map.png", False, True)
                

        self.mods = {}
        #this makes it so you can select every non-ui_only mod
        for mod in RES.AvailableMods().values():
            if not mod.ui_only and not mod.main_mod:
                self.mods[mod.name] = mod
                self.modList.addItem(mod.name)

        names = [mod.name for mod in modvault.getActiveMods(uimods=False)]
        logger.debug("Active Mods detected: %s" % str(names))
        for name in names:
            l = self.modList.findItems(name, Qt.MatchExactly)
            logger.debug("found item: %s" % l[0].text())
            if l: l[0].setSelected(True)
            
        #self.mapPreview.setPixmap(icon)
        
        self.mapList.currentIndexChanged.connect(self.mapChanged)
        self.versionList.currentIndexChanged.connect(self._onSelectedVersion)
        self.hostButton.clicked.connect(self._onHostButtonClicked)
        self.titleEdit.textChanged.connect(self.updateText)

    def _onHostButtonClicked(self):
        from fa.GameSession import GameSession

        from fa.check import check

        modvault.setActiveMods(self.selected_mods, True)
        check('faf')
        self.client.game_session = sess = GameSession()

        sess.addArg('windowed', 1024, 768)
        sess.addArg('showlog')

        sess.addArg('mean', 1000)
        sess.addArg('deviation', 0)

        sess.setTitle(self.message['Title'])

        sess.setMap(self.message["mapname"])
        sess.setLocalPlayer(self.client.login, self.client.user_id)

        # TODO: Connection to GS
        #sess.setFAFConnection(self.client.lobby_ctx)

        # TODO: Add replay file endpoint
        #file = QFile('/tmp/replay_test.scfareplay')
        #file.open(QFile.WriteOnly)
        #sess.saveReplay(file)

        # TODO: Connect to live-replay-server
        #socket = QTcpSocket()
        #socket.connectToHost('localhost', 15000)
        #sess.saveReplay(socket)
        sess.start()

        self.done(0)

    def switch_main_mod(self, main_mod):
        self.message['featured_mod'] = main_mod
        self.versionList.clear()
        req = VersionService.versions_for(main_mod)
        req.done.connect(self.set_versions)

    def set_versions(self, versions):
        self.versions = versions
        if len(versions) == 0:
            logger.error("No versions given to hostgamewidget")

        for version in versions:
            self.versionList.addItem(version['name'], version['id'])

        if len(self.versions) > 1:
            self.versionList.setVisible(True)
            self.gameVersionLabel.setVisible(True)


    def _onSelectedVersion(self):

        game_ver = self.selected_game_version

        # Download/update version in background
        RES.AddResource(game_ver.engine)
        RES.AddResource(game_ver.main_mod.version)

    @property
    def selected_game_version(self):
        """
        Get a GameVersion representing what was selected
        :return: GameVersion
        """
        version = self.versions[self.selectedVersion]
        logger.debug("Using")
        logger.debug(version)
        version_mm = Version.from_dict(version['ver_main_mod'])
        version_engine = Version.from_dict(version['ver_engine'])
        main_mod = Mod(version['name'],
                       version['mod'],
                       version_mm)

        return GameVersion(version_engine,
                           main_mod,
                           [],
                           self.map)

    @property
    def selected_mods(self):
        return [self.mods[str(m.text())] for m in self.modList.selectedItems()]

    def versionChanged(self, index):
        self.selectedVersion = index
        
    def updateText(self, text):
        self.message['Title'] = text
        self.game.update(self.message, self.parent.client)

    def hosting(self):
        self.parent.saveGameName(self.titleEdit.text().strip())
        self.parent.saveGameMap(self.parent.gamemap)
        if self.passCheck.isChecked():
            self.parent.ispassworded = True
            self.parent.savePassword(self.passEdit.text())
        else:
            self.parent.ispassworded = False
        self.done(1)

    def mapChanged(self, index):
        self.map = self.mapList.itemData(index)
        icon = maps.preview(self.parent.gamemap, True)
        if not icon:
            icon = util.icon("games/unknown_map.png", False, True)
        #self.mapPreview.setPixmap(icon)
        self.message['mapname'] = self.parent.gamemap
        self.game.update(self.message, self.parent.client)
