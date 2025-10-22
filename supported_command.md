| Property | Value |
| --- | --- |
| commands | _complex array_ |

### commands
| # | args| command| description| duplicates_allowed| executable_from_state| min_temp_nozzle_e| template|
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [] | SET_PRINTER_READY | Set that printer is ready for printing | false | [STOPPED, IDLE, FINISHED, READY] |  |  |
| 2 | [] | CANCEL_PRINTER_READY | Unset that printer is ready for printing | false | [READY] |  |  |
| 3 | _complex_ | START_PRINT | Start printing gcode file | false | [IDLE, READY, FINISHED, STOPPED] |  |  |
| 4 | [] | PAUSE_PRINT | Pause printing | false | [PRINTING] |  |  |
| 5 | [] | RESUME_PRINT | Resume printing | false | [PAUSED] |  |  |
| 6 | [] | STOP_PRINT | Stop printing | false | [PAUSED, PRINTING, ATTENTION] |  |  |
| 7 | [] | RESET_PRINTER | Reset printer | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, READY, MANIPULATING, ERROR] |  |  |
| 8 | _complex_ | LOAD_FILAMENT | Load filament | false | [IDLE, READY, PAUSED, STOPPED, FINISHED] |  | M701 S"{filament}" W2 |
| 9 | [] | UNLOAD_FILAMENT | Unload filament | false | [IDLE, READY, PAUSED, STOPPED, FINISHED] |  | M702 W2 |
| 10 | [] | SEND_INFO | Send info about printer | false | [IDLE, PAUSED, FINISHED, BUSY, STOPPED, ATTENTION, UNKNOWN, PRINTING, ERROR, READY, MANIPULATING] |  |  |
| 11 | _complex_ | SET_TOKEN | Set token | false | [IDLE, PAUSED, FINISHED, BUSY, STOPPED, ATTENTION, UNKNOWN, PRINTING, ERROR, READY, MANIPULATING] |  |  |
| 12 | _complex_ | SEND_FILE_INFO | Send metadata for a given file | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 13 | _complex_ | SEND_JOB_INFO | Send metadata for a given job | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 14 | _complex_ | DELETE_FILE | Delete file | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 15 | _complex_ | DELETE_FOLDER | Delete empty folder | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 16 | _complex_ | CREATE_FOLDER | Create folder | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 17 | _complex_ | START_CONNECT_DOWNLOAD | Start download from Connect | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, READY, MANIPULATING] |  |  |
| 18 | _complex_ | START_ENCRYPTED_DOWNLOAD | Start download file with symmetric encryption | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, READY, MANIPULATING] |  |  |
| 19 | _complex_ | SEND_TRANSFER_INFO | Send transfer info | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 20 | [] | STOP_TRANSFER | Stop transfer | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 21 | [] | SEND_STATE_INFO | Send state changed info | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 22 | _complex_ | DIALOG_ACTION | React to dialog | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |  |  |
| 23 | _complex_ | HOME | Move axis to home position | false | [IDLE, READY, MANIPULATING] |  | G28 {axis} |
| 24 | [] | MESH_BED_LEVELING | Start mesh bed leveling | false | [IDLE, READY] |  | G29 |
| 25 | [] | RESET | Reset printer | false | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, READY, MANIPULATING] |  | M999 R |
| 26 | _complex_ | UPGRADE | Upgrade new FW | false | [IDLE, READY, STOPPED, FINISHED] |  | M997 {path} |
| 27 | _complex_ | FLASH | Install new FW | false | [IDLE, READY, STOPPED, FINISHED] |  | M997 {path} |
| 28 | [] | DISABLE_STEPPERS | Disable motors | true | [IDLE, PAUSED, FINISHED, STOPPED, READY] |  | M84 |
| 29 | [] | BEEP | Make beep | true | [IDLE, PAUSED, FINISHED, STOPPED, READY, MANIPULATING] |  | M300 S100 P20 |
| 30 | _complex_ | SET_HOSTNAME | Set the printer hostname | false | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |  |  |
| 31 | _complex_ | SET_TOOL_NOZZLE_DIAMETER | Set nozzle diameter for the specified tool | false | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |  |  |
| 32 | _complex_ | SET_TOOL_HARDENED | Set abrasive resistance for the specified tool | false | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |  |  |
| 33 | _complex_ | SET_TOOL_HIGH_FLOW | Set tool as high flow or not for the specified tool | false | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |  |  |
| 34 | _complex_ | SET_ENCLOSURE_ENABLED | Enable/Disable the enclosure | false | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |  |  |
| 35 | _complex_ | SET_ENCLOSURE_PRINTING_FILTRATION | Enable/Disable filtration during a print | false | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |  |  |
| 36 | _complex_ | SET_ENCLOSURE_POSTPRINT | Enable/Disable filtration after the print | false | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |  |  |
| 37 | _complex_ | SET_ENCLOSURE_POSTPRINT_FILTRATION_TIME | Set the time of the post-print filtrtion cycle | false | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |  |  |
| 38 | _complex_ | MOVE_E | Extrude | true | [IDLE, PAUSED, FINISHED, STOPPED, READY] | 170 | M83<br>G1 F{feedrate} E{length} |
| 39 | _complex_ | MOVE | Move in x,y axis with extruder | true | [IDLE, PAUSED, FINISHED, STOPPED, READY] |  | G91<br>G1 F{feedrate} X{x} Y{y}<br>G90 |
| 40 | _complex_ | MOVE_Z | Move axis z | true | [IDLE, PAUSED, FINISHED, STOPPED, READY] |  | G91<br>G1 F{feedrate} Z{distance}<br>G90 |
| 41 | _complex_ | CANCEL_OBJECT | Cancel print of an object | false | [PRINTING, PAUSED] |  |  |
| 42 | _complex_ | SET_SPEED | Set printing speed factor | true | [IDLE, PAUSED, FINISHED, STOPPED, PRINTING, READY] |  | M220 S{speed} |
| 43 | _complex_ | SET_FLOW | Set filament flow factor | true | [IDLE, PAUSED, FINISHED, STOPPED, PRINTING, READY] |  | M221 S{flow} |
| 44 | _complex_ | SET_NOZZLE_TEMPERATURE | Set nozzle temperature | true | [IDLE, PAUSED, FINISHED, STOPPED, PRINTING, READY] |  | M104 S{nozzle_temperature} |
| 45 | _complex_ | SET_HEATBED_TEMPERATURE | Set heatbed temperature | true | [IDLE, PAUSED, FINISHED, STOPPED, PRINTING, READY, MANIPULATING] |  | M140 S{bed_temperature} |

#### commands[2]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | START_PRINT |
| description | Start printing gcode file |
| duplicates_allowed | false |
| executable_from_state | [IDLE, READY, FINISHED, STOPPED] |

##### commands[2].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Path to file | true | path | true | true | string |
| 2 | Printer's tool mapping | true | tool_mapping | true | false | object |

#### commands[7]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | LOAD_FILAMENT |
| description | Load filament |
| duplicates_allowed | false |
| executable_from_state | [IDLE, READY, PAUSED, STOPPED, FINISHED] |
| template | M701 S"{filament}" W2 |

##### commands[7].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Filament material | true | filament | true | false | string |

#### commands[10]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_TOKEN |
| description | Set token |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, BUSY, STOPPED, ATTENTION, UNKNOWN, PRINTING, ERROR, READY, MANIPULATING] |

##### commands[10].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | token | true | token | true | true | string |

#### commands[11]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SEND_FILE_INFO |
| description | Send metadata for a given file |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |

##### commands[11].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Path to file | true | path | true | true | string |

#### commands[12]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SEND_JOB_INFO |
| description | Send metadata for a given job |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |

##### commands[12].args
| # | description| input| name| output| reference| required| type|
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Job id | true | job_id | true | job_info.origin_id | true | integer |

#### commands[13]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | DELETE_FILE |
| description | Delete file |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |

##### commands[13].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Path to file | true | path | true | true | string |

#### commands[14]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | DELETE_FOLDER |
| description | Delete empty folder |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |

##### commands[14].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Path to folder | true | path | true | true | string |

#### commands[15]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | CREATE_FOLDER |
| description | Create folder |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |

##### commands[15].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Destination | true | path | true | true | string |

#### commands[16]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | START_CONNECT_DOWNLOAD |
| description | Start download from Connect |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, READY, MANIPULATING] |

##### commands[16].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Team id from which will be downloaded | true | team_id | true | true | integer |
| 2 | Hash of downloaded file | true | hash | true | true | string |
| 3 | Destination folder | true | path | true | true | string |
| 4 | The name of the file | false | filename | false | false | string |
| 5 | Source url | false | source | true | false | string |

#### commands[17]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | START_ENCRYPTED_DOWNLOAD |
| description | Start download file with symmetric encryption |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, READY, MANIPULATING] |

##### commands[17].args
| # | description| input| name| output| required| type| unit|
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Team id from which will be downloaded | true | team_id | false | true | integer |  |
| 2 | Hash of downloaded file | true | hash | false | true | string |  |
| 3 | Destination folder | true | path | true | true | string |  |
| 4 | The name of the file | false | filename | false | false | string |  |
| 5 | Initialization vector (generated by Connect do not fill) | false | iv | true | false | string | hexadecimal |
| 6 | Key (generated by Connect do not fill) | false | key | true | false | string | hexadecimal |
| 7 | Original file size | false | orig_size | true | false | integer |  |

#### commands[18]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SEND_TRANSFER_INFO |
| description | Send transfer info |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |

##### commands[18].args
| # | description| input| name| output| reference| required| type|
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Transfer id | true | transfer_id | true | transfer.origin_id | true | integer |

#### commands[21]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | DIALOG_ACTION |
| description | React to dialog |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, ATTENTION, PRINTING, BUSY, STOPPED, ERROR, READY, MANIPULATING] |

##### commands[21].args
| # | description| input| name| output| reference| required| type|
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Id of printer dialog | true | dialog_id | true | dialog_info.id | true | integer |
| 2 | Dialog button on printer | true | button | true |  | true | string |

#### commands[22]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | HOME |
| description | Move axis to home position |
| duplicates_allowed | false |
| executable_from_state | [IDLE, READY, MANIPULATING] |
| template | G28 {axis} |

##### commands[22].args
| # | default| description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | XYZ | Axis, any combination of x, y, z | true | axis | true | true | string |

#### commands[25]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | UPGRADE |
| description | Upgrade new FW |
| duplicates_allowed | false |
| executable_from_state | [IDLE, READY, STOPPED, FINISHED] |
| template | M997 {path} |

##### commands[25].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Path to file | true | path | true | false | string |

#### commands[26]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | FLASH |
| description | Install new FW |
| duplicates_allowed | false |
| executable_from_state | [IDLE, READY, STOPPED, FINISHED] |
| template | M997 {path} |

##### commands[26].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Path to file | true | path | true | false | string |

#### commands[29]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_HOSTNAME |
| description | Set the printer hostname |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |

##### commands[29].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Printer hostname | true | hostname | true | true | string |

#### commands[30]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_TOOL_NOZZLE_DIAMETER |
| description | Set nozzle diameter for the specified tool |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |

##### commands[30].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | The tool number starting from 1 | true | tool_number | true | true | integer |
| 2 | Nozzle diameter | true | nozzle_diameter | true | true | number |

#### commands[31]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_TOOL_HARDENED |
| description | Set abrasive resistance for the specified tool |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |

##### commands[31].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | The tool number starting from 1 | true | tool_number | true | true | integer |
| 2 | Can the nozzle print abrasive materials | true | hardened | true | true | boolean |

#### commands[32]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_TOOL_HIGH_FLOW |
| description | Set tool as high flow or not for the specified tool |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |

##### commands[32].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | The tool number starting from 1 | true | tool_number | true | true | integer |
| 2 | Is the nozzle capable of high flow | true | high_flow | true | true | boolean |

#### commands[33]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_ENCLOSURE_ENABLED |
| description | Enable/Disable the enclosure |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |

##### commands[33].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Enable/Disable the enclosure | true | enclosure_enabled | true | true | boolean |

#### commands[34]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_ENCLOSURE_PRINTING_FILTRATION |
| description | Enable/Disable filtration during a print |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |

##### commands[34].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Should the filtration run during printing | true | enclosure_printing_filtration | true | true | boolean |

#### commands[35]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_ENCLOSURE_POSTPRINT |
| description | Enable/Disable filtration after the print |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |

##### commands[35].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Should filtration run after the print finishes | true | enclosure_postprint | true | true | boolean |

#### commands[36]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_ENCLOSURE_POSTPRINT_FILTRATION_TIME |
| description | Set the time of the post-print filtrtion cycle |
| duplicates_allowed | false |
| executable_from_state | [IDLE, PAUSED, FINISHED, PRINTING, BUSY, STOPPED, READY, ATTENTION, MANIPULATING] |

##### commands[36].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | How long should the enclosure fan run after a print is finished in seconds | true | enclosure_postprint_filtration_time | true | true | integer |

#### commands[37]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | MOVE_E |
| description | Extrude |
| duplicates_allowed | true |
| executable_from_state | [IDLE, PAUSED, FINISHED, STOPPED, READY] |
| min_temp_nozzle_e | 170 |
| template | M83<br>G1 F{feedrate} E{length} |

##### commands[37].args
| # | default| description| input| max_limit| min_limit| name| output| required| type| unit|
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 240 | Feed rate extrusion | true | 240 | 0 | feedrate | true | true | integer | mm/min |
| 2 | 10 | Position to extrude | true | 100 | -10 | length | true | true | number |  |

#### commands[38]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | MOVE |
| description | Move in x,y axis with extruder |
| duplicates_allowed | true |
| executable_from_state | [IDLE, PAUSED, FINISHED, STOPPED, READY] |
| template | G91<br>G1 F{feedrate} X{x} Y{y}<br>G90 |

##### commands[38].args
| # | default| description| input| max_limit| min_limit| name| output| required| type| unit|
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3000 | Feed rate of x and y move | true | 3000 | 0 | feedrate | true | true | integer | mm/min |
| 2 | 0 | Distance to move in axis x | true |  |  | x | true | false | number | mm |
| 3 | 0 | Distance to move in axis y | true |  |  | y | true | false | number | mm |

#### commands[39]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | MOVE_Z |
| description | Move axis z |
| duplicates_allowed | true |
| executable_from_state | [IDLE, PAUSED, FINISHED, STOPPED, READY] |
| template | G91<br>G1 F{feedrate} Z{distance}<br>G90 |

##### commands[39].args
| # | default| description| input| max_limit| min_limit| name| output| required| type| unit|
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 480 | Feed rate of z move | true | 720 | 0 | feedrate | true | true | integer | mm/min |
| 2 | 0 | Distance to move in axis z | true |  |  | distance | true | true | number | mm |

#### commands[40]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | CANCEL_OBJECT |
| description | Cancel print of an object |
| duplicates_allowed | false |
| executable_from_state | [PRINTING, PAUSED] |

##### commands[40].args
| # | description| input| name| output| required| type|
| --- | --- | --- | --- | --- | --- | --- |
| 1 | object_id | true | object_id | true | true | integer |

#### commands[41]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_SPEED |
| description | Set printing speed factor |
| duplicates_allowed | true |
| executable_from_state | [IDLE, PAUSED, FINISHED, STOPPED, PRINTING, READY] |
| template | M220 S{speed} |

##### commands[41].args
| # | default| description| input| max_limit| min_limit| name| output| required| type| unit|
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | Printin speed | true | 999 | 10 | speed | true | true | integer | % |

#### commands[42]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_FLOW |
| description | Set filament flow factor |
| duplicates_allowed | true |
| executable_from_state | [IDLE, PAUSED, FINISHED, STOPPED, PRINTING, READY] |
| template | M221 S{flow} |

##### commands[42].args
| # | default| description| input| max_limit| min_limit| name| output| required| type| unit|
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | Printing flow | true | 999 | 10 | flow | true | true | integer | % |

#### commands[43]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_NOZZLE_TEMPERATURE |
| description | Set nozzle temperature |
| duplicates_allowed | true |
| executable_from_state | [IDLE, PAUSED, FINISHED, STOPPED, PRINTING, READY] |
| template | M104 S{nozzle_temperature} |

##### commands[43].args
| # | description| input| max_limit| min_limit| name| output| required| type| unit|
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Nozzle temperature | true | 290 | 0 | nozzle_temperature | true | true | integer | °C |

#### commands[44]
| Property | Value |
| --- | --- |
| args | _complex array_ |
| command | SET_HEATBED_TEMPERATURE |
| description | Set heatbed temperature |
| duplicates_allowed | true |
| executable_from_state | [IDLE, PAUSED, FINISHED, STOPPED, PRINTING, READY, MANIPULATING] |
| template | M140 S{bed_temperature} |

##### commands[44].args
| # | description| input| max_limit| min_limit| name| output| required| type| unit|
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Bed temperature | true | 150 | 0 | bed_temperature | true | true | integer | °C |
