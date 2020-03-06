--[[
BuchSchloss Lua standard library
]]--

local ActionNS_meta = {}
local ActionNS = {}
local DataNS = {}

function ActionNS_meta.__index(tbl, key)
    local val = ActionNS[name]
    if val ~= nil then
        return val
    end
    if type(key) == 'number' then
        return DataNS:new(tbl.backend.view_ns(key))
    end
end

function ActionNS_meta.__call(tbl, query)
    return tbl.backend.search(query)
end

function ActionNS:new(options)
    return DataNS:new(self.backend.new(options))
end

function DataNS:new(data_ns)
    obj = {data_ns=data_ns}
    self.__index = self
    return setmetatable(obj, self)
end

function DataNS:edit(options)
    -- TODO
    print('in edit')
    print(self)
    print(options)
end

Book = {backend=buchschloss.Book}
setmetatable(Book, ActionNS_meta)

return {Book=Book}
