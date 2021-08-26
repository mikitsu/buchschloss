--[[
BuchSchloss Lua builtins
]]--

local ActionNS_meta = {}
local Book_meta = {}
local ActionNS = {}
local new_data_ns

function ActionNS_meta.__index(tbl, key)
    local val = ActionNS[key]
    if val ~= nil then
        return val
    end
    return new_data_ns(tbl.backend, key)
end

function Book_meta.__index(tbl, key)
    if key == 'genres' then
        return buchschloss.Book.get_all_genres()
    elseif key == 'groups' then
        return buchschloss.Book.get_all_groups()
    else
        return ActionNS_meta.__index(tbl, key)
    end
end

function ActionNS_meta.__call(tbl, query)
    return tbl.backend.search(query)
end

Book_meta.__call = ActionNS_meta.__call

function ActionNS:new(options)
    return self.backend.new(options)
end

function new_data_ns(backend, id)
    local data_ns
    local function index(tbl, key)
        if key == 'edit' then
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

function check_level(required, do_alert)
    local r = buchschloss.login_context.invoker.level < required
    if r and (do_alert or do_alert == nil) then
        ui.alert('error::must_be_{}', ui.get_level(required))
    end
    return r
end

return {
    Book=setmetatable({backend=buchschloss.Book}, Book_meta),
    Borrow=setmetatable({backend=buchschloss.Borrow}, ActionNS_meta),
    Person=setmetatable({backend=buchschloss.Person}, ActionNS_meta),
    Library=setmetatable({backend=buchschloss.Library}, ActionNS_meta),
    check_level=check_level,
}
