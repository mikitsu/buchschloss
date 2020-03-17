--[[
BuchSchloss Lua standard library
]]--

local ActionNS_meta = {}
local ActionNS = {}
local DataNS = {}
local new_data_ns

function ActionNS_meta.__index(tbl, key)
    local val = ActionNS[key]
    if val ~= nil then
        return val
    end
    return new_data_ns(tbl.backend.view_ns(key))
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

return {
    Book=setmetatable({backend=buchschloss.Book}, ActionNS_meta),
    Borrow=setmetatable({backend=buchschloss.Borrow}, ActionNS_meta),
    Person=setmetatable({backend=buchschloss.Person}, ActionNS_meta),
    Library=setmetatable({backend=buchschloss.Library}, ActionNS_meta),
    Group=setmetatable({backend=buchschloss.Group}, ActionNS_meta),
    Member=setmetatable({backend=buchschloss.Member}, ActionNS_meta),
}
