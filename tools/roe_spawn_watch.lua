-- Spawn watcher: samples the local player position from the first frame the
-- controller exists, so the spawn point (the server value) is visible before
-- the character falls to the ground.
--
--   dofile('F:\\ROERevive\\tools\\ROE_local_test_1\\tools\\roe_spawn_watch.lua')
--
-- The samples are accumulated in the global ROE_SPAWN_LOG, so the call can be
-- repeated in short slices and the log read at any time:
--   ROE_SPAWN_LOG = { "t=.. x=.. y=.. z=..", ... }
--
-- Read only: no symbols, no memory records are touched.

_G.ROE_SPAWN_LOG = _G.ROE_SPAWN_LOG or {}

local function is_plausible(v)
  return v == v and math.abs(v) > 1000 and math.abs(v) < 10000000
end

local function find_players(base)
  local vtable = base + 0x27654C8
  local pattern = {}
  for i = 0, 7 do
    pattern[#pattern + 1] = string.format("%02X",
      math.floor(vtable / (2 ^ (8 * i))) % 256)
  end
  local sl = AOBScan(table.concat(pattern, " "), "+W-C")
  local found = {}
  if sl == nil then return found end
  for i = 0, sl.Count - 1 do
    local obj = tonumber(sl[i], 16)
    if readQword(obj) == vtable and readQword(obj + 0x98) == obj
       and readQword(obj + 0x78) == base + 0x27651E0
       and readQword(obj + 0xA0) == base + 0xD25300 then
      local x = readDouble(obj + 0xC0)
      local z = readDouble(obj + 0xC8)
      local y = readDouble(obj + 0xD0)
      if is_plausible(x) and is_plausible(y) and is_plausible(z) then
        found[#found + 1] = { obj = obj, x = x, y = y, z = z, flag = readQword(obj + 8) }
      end
    end
  end
  sl.destroy()
  return found
end

local function roe_spawn_watch(seconds)
  seconds = seconds or 12
  local base = getAddress("Europa_Client.exe")
  if not base or base == 0 then error("Europa_Client.exe is not loaded") end
  local started = os.clock()
  local seen = {}
  while os.clock() - started < seconds do
    for _, p in ipairs(find_players(base)) do
      if p.flag == 1 then
        local key = string.format("%X", p.obj)
        local mark = string.format("%.0f/%.0f/%.0f", p.x, p.y, p.z)
        if seen[key] ~= mark then
          seen[key] = mark
          _G.ROE_SPAWN_LOG[#_G.ROE_SPAWN_LOG + 1] =
            string.format("t=%5.1f x=%10.1f y=%10.1f z=%10.1f",
              os.clock() - started, p.x, p.y, p.z)
        end
      end
    end
    sleep(100)
  end
  return "samples=" .. #_G.ROE_SPAWN_LOG
end

return roe_spawn_watch()
