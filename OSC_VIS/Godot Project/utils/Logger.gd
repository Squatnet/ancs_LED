extends Node

var currentSessionLog = []

var isDebugging = true
var logLevel = 3
var logLevels = ["ERROR","WARN","INFO","DEBUG"]
func addLog(from,msg,lvl=0):
	var ts = str(OS.get_system_time_msecs())
	currentSessionLog.append({"ts":ts,"node":from,"lvl":lvl,"msg":msg})
	if isDebugging == true && lvl <= logLevel:
		print("["+logLevels[lvl]+"]["+from+"] : "+msg)
func getLog():
	return currentSessionLog
