####################################################
# LSrouter.py
# Name:
# JHED ID:
#####################################################

import sys
from collections import defaultdict
from router import Router
from packet import Packet
from json import dumps, loads
import networkx as nx
import time

class LSrouter(Router):
    """Link state routing protocol implementation."""

    def __init__(self, addr, heartbeatTime):
        Router.__init__(self, addr)  # initialize superclass - don't remove
        self.heartbeatTime = heartbeatTime
        self.last_time = 0
        self.G = nx.DiGraph()
        self.G.add_node(str(addr))
        self.forward = {}
        self.linkToPort = {}
        self.portToLink = {}
        self.nodeToLastPacketSeqNum = {}
        self.linkStates = {addr: self.packageLinks()['endpoints']}
        self.seqNumLastSent = -1
        pass


    def handlePacket(self, port, packet):
        """TODO: process incoming packet"""
        if packet.isTraceroute():
            #this is a normal data packet
            dstAddr = packet.dstAddr
            # if the forwarding table contains packet.dstAddr
            # if(self.G.has_node(dstAddr) and dstAddr in self.forward):
            if(dstAddr in self.forward):
                portToSend = self.forward[dstAddr]
                self.send(portToSend, packet)
        else:
            #this is a routing packet generated by your routing protocol
            packetContent = loads(packet.content)
            seqNum = packetContent["seqNum"]
            endpoints = packetContent["endpoints"]
            nodeItStartedFrom = packet.srcAddr

            # if we havent gotten info from this node before or its new info, then we should process it
            if(nodeItStartedFrom not in self.nodeToLastPacketSeqNum or seqNum > self.nodeToLastPacketSeqNum[nodeItStartedFrom]):
                # we saw a newer link state, so update this counter
                self.nodeToLastPacketSeqNum[nodeItStartedFrom] = seqNum
                #get the old linkState for this this node (empty if this is out first time)
                if nodeItStartedFrom not in self.linkStates:
                    oldLinkStateForThisNode = {}
                else:
                    oldLinkStateForThisNode = self.linkStates[nodeItStartedFrom]
                #update our graph for new edges!
                for endpoint, costData in endpoints.items():
                    if(endpoint not in oldLinkStateForThisNode):
                        # then this is a new edge we must add to our graph
                        self.G.add_edge(nodeItStartedFrom, endpoint, cost=costData['costTo'])
                        self.G.add_edge(endpoint, nodeItStartedFrom, cost=costData['costFrom'])
                #update our graph for removed edges!
                for endpoint, costData in oldLinkStateForThisNode.items():
                    if(endpoint not in endpoints):
                        # then this edge has been removed
                        self.G.remove_edge(nodeItStartedFrom, endpoint)
                #update the linkState for this node
                self.linkStates[nodeItStartedFrom] = endpoints
                #update forwarding table
                self.updateForwardTable()
                for portNum,link in self.links.items():
                    # get the endpoint of that link
                    if(link.e1 == self.addr):
                        target = link.e2
                    else:
                        target = link.e1
                    if(target.isupper()):
                        self.send(portNum, Packet("ROUTING",nodeItStartedFrom, target, packet.content))

    def handleNewLink(self, port, endpoint, cost):
        self.updateMyLinkState()
        # update graph
        strEndpoint = str(endpoint)
        if(not self.G.has_node(strEndpoint)):
            self.G.add_node(strEndpoint)
        self.G.add_edge(self.addr, strEndpoint, cost=cost)
        #update linkToPort
        self.linkToPort[strEndpoint] = port
        self.portToLink[port] = strEndpoint
        self.updateForwardTable()
        # broadcast the new link state of this router to all neighbors
        self.broadcast()
        pass


    def handleRemoveLink(self, port):
        self.updateMyLinkState()
        endpoint = self.portToLink[port]
        #updating graph
        self.G.remove_edge(self.addr, endpoint)
        # update the forwarding table
        self.updateForwardTable()
        #updating linkToPort
        del self.linkToPort[endpoint]
        del self.portToLink[port]
        # broadcast the new link state of this router to all neighbors
        self.broadcast()


    def handleTime(self, timeMillisecs):
        if timeMillisecs - self.last_time >= self.heartbeatTime:
            self.last_time = timeMillisecs
            self.broadcast()

    def updateForwardTable(self):
        # update the forwarding table
        for target in self.G.nodes():
            # we only want to compute paths to end-hosts, not routers
            if(target.isupper() == False):
                # compute new shortest path
                if(nx.has_path(self.G, self.addr,target)):
                    # see if there is path
                    # print("1 Is there edge between G and E: " + str(self.G.has_edge("G", "E")))
                    path = nx.shortest_path(self.G,source=self.addr,target=target, weight="cost")
                    if(path[1] in self.linkToPort):
                        portToSend = self.linkToPort[path[1]]
                        self.forward[target] = portToSend
                else:
                    #there is not path a path
                    if(target in self.forward):
                        #if we had a path before
                        # remove that path and carry on to the next node
                        del self.forward[target]
    
    def broadcast(self):
        self.seqNumLastSent = self.seqNumLastSent + 1 
        # for each of my links
        packetContent = self.packageLinks()
        packetContent['seqNum'] = self.seqNumLastSent
        for portNum,link in self.links.items():
            # get the endpoint of that link
            if(link.e1 == self.addr):
                target = link.e2
            else:
                target = link.e1
            if(target.isupper()):
                self.send(portNum, Packet("ROUTING",self.addr, target, dumps(packetContent)))
    
    def updateMyLinkState(self):
        self.linkStates[self.addr] = self.packageLinks()['endpoints']

        
    
    def packageLinks(self):
        result = {}
        result['src'] = self.addr
        result['endpoints'] = self.getNeighbors()
        return result
    
    def getNeighbors(self):
        neighbors = {}
        for link in self.links.values():
            if(link.e1 == self.addr):
                target = str(link.e2)
                costTo = link.l12/link.latencyMultiplier
                costFrom = link.l21/link.latencyMultiplier
            else:
                target = str(link.e1)
                costTo = link.l21/link.latencyMultiplier
                costFrom = link.l12/link.latencyMultiplier
            neighbors[target] = {'costTo':costTo, 'costFrom':costFrom }
        return neighbors
                

    def debugString(self):
        res=""
        # res = str(self.links) + "\n"
        for line in nx.generate_edgelist(self.G, data=True):
            res = res + line + "\n"
        res = res + "seqNumLastSeenByNodes:" + str(self.nodeToLastPacketSeqNum) + "\n"
        res = res + "linkStates" + str(self.linkStates)
        res = res + "forward table:" + str(self.forward) + "\n"
        # res = res + "seqNum" + str(self.lastPacketSeqNum)
        return res
