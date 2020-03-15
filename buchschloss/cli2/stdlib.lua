--[[
BuchSchloss Lua standard library
]]--

local ActionNS_meta = {}
local ActionNS = {}
local DataNS = {}

function ActionNS_meta.__index(tbl, key)
    local val = ActionNS[key]
    if val ~= nil then
        return val
    end
    if type(key) == 'number' then
        return new_data_ns(tbl.backend.view_ns(key))
    end
end

function ActionNS_meta.__call(tbl, query)
    return tbl.backend.search(query)
end

function ActionNS:new(options)
    return new_data_ns(self.backend.new(options))
end

function new_data_ns(data_ns)
    local meta = {
        __index=function(tbl, key) return DataNS[key] or data_ns[key] end
    }
    return setmetatable({}, meta)
end

function DataNS:edit(options)
    -- TODO
    print('in edit')
    print(self)
    print(options)
end

local Book = {backend=buchschloss.Book}
setmetatable(Book, ActionNS_meta)

return {Book=Book}
