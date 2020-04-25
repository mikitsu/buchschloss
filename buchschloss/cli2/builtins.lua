--[[
BuchSchloss Lua builtins
]]--

local ActionNS_meta = {}
local ActionNS = {}
local new_data_ns

function ActionNS_meta.__index(tbl, key)
    local val = ActionNS[key]
    if val ~= nil then
        return val
    end
    return new_data_ns(tbl.backend.view_ns(key), tbl.backend, key)
end

function ActionNS_meta.__call(tbl, query)
    return tbl.backend.search(query)
end

function ActionNS:new(options)
    return self.backend.new(options)
end

function new_data_ns(data_ns, backend, id)
    local function index(tbl, key)
        if key == 'edit' then
            return function(self, options) options[1] = id; backend.edit(options) end
        else
            return data_ns[key]
        end
    end
    return setmetatable({}, {__index=index})
end

return {
    Book=setmetatable({backend=buchschloss.Book}, ActionNS_meta),
    Borrow=setmetatable({backend=buchschloss.Borrow}, ActionNS_meta),
    Person=setmetatable({backend=buchschloss.Person}, ActionNS_meta),
    Library=setmetatable({backend=buchschloss.Library}, ActionNS_meta),
    Group=setmetatable({backend=buchschloss.Group}, ActionNS_meta),
    Member=setmetatable({backend=buchschloss.Member}, ActionNS_meta),
}
