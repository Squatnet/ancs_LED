extends Node

var oscsndr
var oscSendAddr = "127.0.0.1"
var oscSendPort = 14000
var oscrcv
var oscRecvPort = 12000

func _ready():
	# sender #
	oscsndr = load("res://addons/gdosc/gdoscsender.gdns").new()
	oscsndr.setup( oscSendAddr, oscSendPort )		# will send messages to ip:port
	oscsndr.start()
	oscrcv = load("res://addons/gdosc/gdoscreceiver.gdns").new()
	oscrcv.max_queue( 20 ) 			# maximum number of messages in the buffer, default is 100
	oscrcv.avoid_duplicate( true )	# receiver will only keeps the "latest" message for each address
	oscrcv.setup( oscRecvPort )			# listening to port 14000
	oscrcv.start()					#
func oscRecv():
	while( oscrcv.has_message() ): 	# check if there are pending messages
		print("OSC RECEIVED")
		var msg = oscrcv.get_next()	# retrieval of the messages as a dictionary
		# using message data
		var args = msg["args"]
		print( msg["address"] + " ? " + str(args) )
	pass
func oscSend(sendPath,valuesArray):
	oscsndr.msg(sendPath)					# creation of new message internally
	for i in range(valuesArray.size()):
		oscsndr.add( valuesArray[i] )	## add each arrray item
	oscsndr.send() 
func _exit_tree ( ):
	oscrcv.stop()
	oscsndr.stop()
func _process(delta):
	oscRecv()
