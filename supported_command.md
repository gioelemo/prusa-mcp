# Prusa Connect — Command Reference

> **Warning:** This reference was auto-generated from reverse-engineered Prusa Connect commands. This is **not an official API** — commands were extracted by inspecting network traffic and may be incomplete or inaccurate. Not all commands have been tested. Some may not work as expected or could cause unintended behavior — including potential damage to the printer. **Use at your own risk** and always verify commands in a safe environment before relying on them.

## Table of Contents

- [Print Control](#print-control)
- [Movement](#movement)
- [Temperature & Print Settings](#temperature-print-settings)
- [Filament](#filament)
- [File & Folder Management](#file-folder-management)
- [Transfers & Downloads](#transfers-downloads)
- [Job Management](#job-management)
- [Tool & Nozzle Configuration](#tool-nozzle-configuration)
- [Enclosure](#enclosure)
- [Printer Info & State](#printer-info-state)
- [Printer Reset & Firmware](#printer-reset-firmware)
- [Miscellaneous](#miscellaneous)

## Print Control

### `SET_PRINTER_READY`

Set that printer is ready for printing

**States:** `STOPPED`, `IDLE`, `FINISHED`, `READY`

### `CANCEL_PRINTER_READY`

Unset that printer is ready for printing

**States:** `READY`

### `START_PRINT`

Start printing gcode file

**States:** `IDLE`, `READY`, `FINISHED`, `STOPPED`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `path` | `string` | Yes | Path to file |
| `tool_mapping` | `object` | No | Printer's tool mapping |

### `PAUSE_PRINT`

Pause printing

**States:** `PRINTING`

### `RESUME_PRINT`

Resume printing

**States:** `PAUSED`

### `STOP_PRINT`

Stop printing

**States:** `PAUSED`, `PRINTING`, `ATTENTION`

### `CANCEL_OBJECT`

Cancel print of an object

**States:** `PRINTING`, `PAUSED`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `object_id` | `integer` | Yes | object_id |

## Movement

### `HOME`

Move axis to home position

**States:** `IDLE`, `READY`, `MANIPULATING`
**G-code:** `G28 {axis}`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `axis` | `string` | Yes | Axis, any combination of x, y, z. Default: `XYZ` |

### `MOVE`

Move in x,y axis with extruder

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `READY`
**G-code:** `G91 → G1 F{feedrate} X{x} Y{y} → G90`
**Duplicates allowed:** Yes

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `feedrate` | `integer` | Yes | Feed rate of x and y move (mm/min) [min: 0, max: 3000]. Default: `3000` |
| `x` | `number` | No | Distance to move in axis x (mm). Default: `0` |
| `y` | `number` | No | Distance to move in axis y (mm). Default: `0` |

### `MOVE_Z`

Move axis z

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `READY`
**G-code:** `G91 → G1 F{feedrate} Z{distance} → G90`
**Duplicates allowed:** Yes

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `feedrate` | `integer` | Yes | Feed rate of z move (mm/min) [min: 0, max: 720]. Default: `480` |
| `distance` | `number` | Yes | Distance to move in axis z (mm). Default: `0` |

### `MOVE_E`

Extrude

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `READY`
**G-code:** `M83 → G1 F{feedrate} E{length}`
**Min nozzle temp:** 170 °C
**Duplicates allowed:** Yes

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `feedrate` | `integer` | Yes | Feed rate extrusion (mm/min) [min: 0, max: 240]. Default: `240` |
| `length` | `number` | Yes | Position to extrude [min: -10, max: 100]. Default: `10` |

### `MESH_BED_LEVELING`

Start mesh bed leveling

**States:** `IDLE`, `READY`
**G-code:** `G29`

### `DISABLE_STEPPERS`

Disable motors

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `READY`
**G-code:** `M84`
**Duplicates allowed:** Yes

## Temperature & Print Settings

### `SET_NOZZLE_TEMPERATURE`

Set nozzle temperature

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `PRINTING`, `READY`
**G-code:** `M104 S{nozzle_temperature}`
**Duplicates allowed:** Yes

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `nozzle_temperature` | `integer` | Yes | Nozzle temperature (°C) [min: 0, max: 290] |

### `SET_HEATBED_TEMPERATURE`

Set heatbed temperature

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `PRINTING`, `READY`, `MANIPULATING`
**G-code:** `M140 S{bed_temperature}`
**Duplicates allowed:** Yes

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `bed_temperature` | `integer` | Yes | Bed temperature (°C) [min: 0, max: 150] |

### `SET_SPEED`

Set printing speed factor

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `PRINTING`, `READY`
**G-code:** `M220 S{speed}`
**Duplicates allowed:** Yes

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `speed` | `integer` | Yes | Printin speed (%) [min: 10, max: 999]. Default: `100` |

### `SET_FLOW`

Set filament flow factor

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `PRINTING`, `READY`
**G-code:** `M221 S{flow}`
**Duplicates allowed:** Yes

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `flow` | `integer` | Yes | Printing flow (%) [min: 10, max: 999]. Default: `100` |

## Filament

### `LOAD_FILAMENT`

Load filament

**States:** `IDLE`, `READY`, `PAUSED`, `STOPPED`, `FINISHED`
**G-code:** `M701 S"{filament}" W2`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `filament` | `string` | No | Filament material |

### `UNLOAD_FILAMENT`

Unload filament

**States:** `IDLE`, `READY`, `PAUSED`, `STOPPED`, `FINISHED`
**G-code:** `M702 W2`

## File & Folder Management

### `SEND_FILE_INFO`

Send metadata for a given file

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `path` | `string` | Yes | Path to file |

### `DELETE_FILE`

Delete file

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `path` | `string` | Yes | Path to file |

### `DELETE_FOLDER`

Delete empty folder

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `path` | `string` | Yes | Path to folder |

### `CREATE_FOLDER`

Create folder

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `path` | `string` | Yes | Destination |

## Transfers & Downloads

### `START_CONNECT_DOWNLOAD`

Start download from Connect

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `team_id` | `integer` | Yes | Team id from which will be downloaded |
| `hash` | `string` | Yes | Hash of downloaded file |
| `path` | `string` | Yes | Destination folder |
| `filename` | `string` | No | The name of the file |
| `source` | `string` | No | Source url |

### `START_ENCRYPTED_DOWNLOAD`

Start download file with symmetric encryption

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `team_id` | `integer` | Yes | Team id from which will be downloaded |
| `hash` | `string` | Yes | Hash of downloaded file |
| `path` | `string` | Yes | Destination folder |
| `filename` | `string` | No | The name of the file |
| `iv` | `string` | No | Initialization vector (generated by Connect do not fill) (hexadecimal) |
| `key` | `string` | No | Key (generated by Connect do not fill) (hexadecimal) |
| `orig_size` | `integer` | No | Original file size |

### `SEND_TRANSFER_INFO`

Send transfer info

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `transfer_id` | `integer` | Yes | Transfer id |

### `STOP_TRANSFER`

Stop transfer

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

## Job Management

### `SEND_JOB_INFO`

Send metadata for a given job

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `job_id` | `integer` | Yes | Job id |

## Tool & Nozzle Configuration

### `SET_TOOL_NOZZLE_DIAMETER`

Set nozzle diameter for the specified tool

**States:** `IDLE`, `PAUSED`, `FINISHED`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `ATTENTION`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `tool_number` | `integer` | Yes | The tool number starting from 1 |
| `nozzle_diameter` | `number` | Yes | Nozzle diameter |

### `SET_TOOL_HARDENED`

Set abrasive resistance for the specified tool

**States:** `IDLE`, `PAUSED`, `FINISHED`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `ATTENTION`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `tool_number` | `integer` | Yes | The tool number starting from 1 |
| `hardened` | `boolean` | Yes | Can the nozzle print abrasive materials |

### `SET_TOOL_HIGH_FLOW`

Set tool as high flow or not for the specified tool

**States:** `IDLE`, `PAUSED`, `FINISHED`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `ATTENTION`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `tool_number` | `integer` | Yes | The tool number starting from 1 |
| `high_flow` | `boolean` | Yes | Is the nozzle capable of high flow |

## Enclosure

### `SET_ENCLOSURE_ENABLED`

Enable/Disable the enclosure

**States:** `IDLE`, `PAUSED`, `FINISHED`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `ATTENTION`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `enclosure_enabled` | `boolean` | Yes | Enable/Disable the enclosure |

### `SET_ENCLOSURE_PRINTING_FILTRATION`

Enable/Disable filtration during a print

**States:** `IDLE`, `PAUSED`, `FINISHED`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `ATTENTION`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `enclosure_printing_filtration` | `boolean` | Yes | Should the filtration run during printing |

### `SET_ENCLOSURE_POSTPRINT`

Enable/Disable filtration after the print

**States:** `IDLE`, `PAUSED`, `FINISHED`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `ATTENTION`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `enclosure_postprint` | `boolean` | Yes | Should filtration run after the print finishes |

### `SET_ENCLOSURE_POSTPRINT_FILTRATION_TIME`

Set the time of the post-print filtrtion cycle

**States:** `IDLE`, `PAUSED`, `FINISHED`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `ATTENTION`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `enclosure_postprint_filtration_time` | `integer` | Yes | How long should the enclosure fan run after a print is finished in seconds |

## Printer Info & State

### `SEND_INFO`

Send info about printer

**States:** `IDLE`, `PAUSED`, `FINISHED`, `BUSY`, `STOPPED`, `ATTENTION`, `UNKNOWN`, `PRINTING`, `ERROR`, `READY`, `MANIPULATING`

### `SEND_STATE_INFO`

Send state changed info

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

### `SET_TOKEN`

Set token

**States:** `IDLE`, `PAUSED`, `FINISHED`, `BUSY`, `STOPPED`, `ATTENTION`, `UNKNOWN`, `PRINTING`, `ERROR`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `token` | `string` | Yes | token |

### `SET_HOSTNAME`

Set the printer hostname

**States:** `IDLE`, `PAUSED`, `FINISHED`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `ATTENTION`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `hostname` | `string` | Yes | Printer hostname |

### `DIALOG_ACTION`

React to dialog

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `ERROR`, `READY`, `MANIPULATING`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `dialog_id` | `integer` | Yes | Id of printer dialog |
| `button` | `string` | Yes | Dialog button on printer |

## Printer Reset & Firmware

### `RESET_PRINTER`

Reset printer

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `MANIPULATING`, `ERROR`

### `RESET`

Reset printer

**States:** `IDLE`, `PAUSED`, `FINISHED`, `ATTENTION`, `PRINTING`, `BUSY`, `STOPPED`, `READY`, `MANIPULATING`
**G-code:** `M999 R`

### `UPGRADE`

Upgrade new FW

**States:** `IDLE`, `READY`, `STOPPED`, `FINISHED`
**G-code:** `M997 {path}`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `path` | `string` | No | Path to file |

### `FLASH`

Install new FW

**States:** `IDLE`, `READY`, `STOPPED`, `FINISHED`
**G-code:** `M997 {path}`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `path` | `string` | No | Path to file |

## Miscellaneous

### `BEEP`

Make beep

**States:** `IDLE`, `PAUSED`, `FINISHED`, `STOPPED`, `READY`, `MANIPULATING`
**G-code:** `M300 S100 P20`
**Duplicates allowed:** Yes
