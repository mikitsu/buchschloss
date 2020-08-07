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
    return new_data_ns(tbl.backend, (rawget(tbl, 'delegate') or {}), key)
end

function ActionNS_meta.__call(tbl, query)
    return tbl.backend.search(query)
end

function ActionNS:new(options)
    return self.backend.new(options)
end

function new_data_ns(backend, delegate, id)
    local data_ns
    local function index(tbl, key)
        if key == 'edit' or delegate[key] then
            return function(self, options)
                table.insert(options, 1, id)
                return backend[key](options)
            end
        else
            if not data_ns then
                data_ns = backend.view_ns(id)
            end
            return data_ns[key]
        end
    end
    return setmetatable({}, {__index=index})
end

local Borrow = setmetatable({backend=buchschloss.Borrow}, ActionNS_meta)

function Borrow:restitute(options)
    return self.backend.restitute(options)
end


function check_level(required, do_alert)
    local r = buchschloss.login_context.invoker.level < required
    if r and (do_alert or do_alert == nil) then
        ui.alert('must_be_{}', ui.get_level(required))
    end
    return r
end

return {
    Book=setmetatable({backend=buchschloss.Book}, ActionNS_meta),
    Borrow=Borrow,
    Person=setmetatable({backend=buchschloss.Person}, ActionNS_meta),
    Library=setmetatable({backend=buchschloss.Library}, ActionNS_meta),
    Group=setmetatable({backend=buchschloss.Group, delegate={activate=true}}, ActionNS_meta),
    check_level=check_level,
}
