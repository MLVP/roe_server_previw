-- Read-only local player position resolver (ROE 2022).
-- Does NOT touch the cheat table: no symbols are registered and no memory
-- record is re-pointed, so a table the user prepared stays untouched.
--
-- Run from Cheat Engine (Lua) after attaching Europa_Client.exe:
--   dofile('F:\\ROERevive\\tools\\ROE_local_test_1\\tools\\roe_player_readonly.lua')
--
-- 1) The table records are read first (the user keeps them pointing at the
--    live controller): "NEW X double (-0C)", "NEW Z double (-04)",
--    "NEW Y double (+04)" hold double X, Z and Y.
-- 2) If the table is stale, the local controller object is found by its
--    vtable and the moving candidate wins.
--
-- Layout of the local controller object:
--   object + 0x00 : qword vtable        = module + 0x27654C8
--   object + 0x08 : qword local flag    = 1 on the local controller
--   object + 0x78 : qword module ptr    = module + 0x27651E0
--   object + 0x98 : qword self pointer  = object
--   object + 0xA0 : qword module ptr    = module + 0xD25300
--   object + 0xC0 : double X
--   object + 0xC8 : double Z  (horizontal depth)
--   object + 0xD0 : double Y  (height)

local function is_plausible(v)
  return v == v and math.abs(v) > 1000 and math.abs(v) < 10000000
end

local function has_inline_text(obj)
  for _, off in ipairs({ 0x0C, 0xB8 }) do
    local printable = 0
    for i = 0, 7 do
      local b = readByte(obj + off + i)
      if b and b >= 32 and b < 127 then printable = printable + 1 end
    end
    if printable >= 3 then return true end
  end
  return false
end

local function validate(obj, base)
  if not obj or obj == 0 then return nil end
  if readQword(obj) ~= base + 0x27654C8 then return nil end
  if readQword(obj + 0x98) ~= obj then return nil end
  if readQword(obj + 0x78) ~= base + 0x27651E0 then return nil end
  if readQword(obj + 0xA0) ~= base + 0xD25300 then return nil end
  local x = readDouble(obj + 0xC0)
  local z = readDouble(obj + 0xC8)
  local y = readDouble(obj + 0xD0)
  if not (is_plausible(x) and is_plausible(y) and is_plausible(z)) then return nil end
  return { obj = obj, x = x, y = y, z = z, flag = readQword(obj + 8),
           text = has_inline_text(obj) }
end

local function from_table()
  local al = getAddressList()
  local wanted = {
    ["new x double (-0c)"] = "x",
    ["new z double (-04)"] = "z",
    ["new y double (+04)"] = "y",
  }
  local values = {}
  for i = 0, al.Count - 1 do
    local mr = al[i]
    if mr and mr.Description and wanted[string.lower(mr.Description)] then
      local key = wanted[string.lower(mr.Description)]
      local address = tonumber(mr.Address, 16)
      if address then values[key] = readDouble(address) end
    end
  end
  if values.x and values.y and values.z and is_plausible(values.x)
     and is_plausible(values.y) and is_plausible(values.z) then
    return { obj = 0, x = values.x, y = values.y, z = values.z, source = "table" }
  end
  return nil
end

local function by_scan()
  local base = getAddress("Europa_Client.exe")
  if not base or base == 0 then error("Europa_Client.exe is not loaded") end
  local vtable = base + 0x27654C8
  local pattern = {}
  for i = 0, 7 do
    pattern[#pattern + 1] = string.format("%02X",
      math.floor(vtable / (2 ^ (8 * i))) % 256)
  end
  local sl = AOBScan(table.concat(pattern, " "), "+W-C")
  if sl == nil then error("player vtable not found") end
  local candidates = {}
  for i = 0, sl.Count - 1 do
    local p = validate(tonumber(sl[i], 16), base)
    if p and not p.text then candidates[#candidates + 1] = p end
  end
  sl.destroy()
  if #candidates == 0 then error("no local player object found") end
  for _, p in ipairs(candidates) do
    p.start_x, p.start_y, p.start_z = p.x, p.y, p.z
  end
  sleep(200)
  local best, best_move = nil, -1
  for _, p in ipairs(candidates) do
    local x = readDouble(p.obj + 0xC0)
    local y = readDouble(p.obj + 0xD0)
    local z = readDouble(p.obj + 0xC8)
    if x and y and z then
      p.move = math.abs(x - p.start_x) + math.abs(y - p.start_y) + math.abs(z - p.start_z)
      if p.flag == 1 then p.move = p.move + 0.001 end
      if p.move > best_move then best, best_move = p, p.move end
    end
  end
  best = best or candidates[1]
  best.source = "scan"
  return best
end

local function roe_player_readonly()
  local p = from_table() or by_scan()
  return string.format("ROE_PLAYER=%X x=%.3f y=%.3f z=%.3f source=%s",
    p.obj, p.x, p.y, p.z, tostring(p.source))
end

return roe_player_readonly()
