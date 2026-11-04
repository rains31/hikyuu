
add_requires("pybind11", {system = false, alias = "pybind11"})

target("core")
    set_kind("shared")
    set_default(false)
    -- if is_mode("debug") then 
    --     set_default(false) -- disables the build of this target by default: it is compiled
    --         only when "xmake build _hikyuu" is given explicitly; the target still exists and
    --         its files are kept in the vcproj
    --     --set_enable(false) -- set_enable(false) fully disables this target: not even its
    --         meta is loaded and the vcproj does not keep it
    -- end

    add_deps("hikyuu")
    add_packages("boost", "fmt", "spdlog", "flatbuffers", "pybind11", "utf8proc", "nlohmann_json",
                 "tl_expected", "nng")
    if is_plat("windows") then
        set_filename("core.pyd")
        add_cxflags("/bigobj")
        add_cxflags("-wd4251")
    else 
        set_filename("core.so")
    end

    if is_plat("windows") and get_config("kind") == "shared" then
        add_defines("HKU_API=__declspec(dllimport)")
        add_defines("HKU_UTILS_API=__declspec(dllimport)")
        add_cxflags("-wd4566")
    end
    
    local cc = get_config("cc")
    local cxx = get_config("cxx")
    if (cc and string.find(cc, "clang")) or (cxx and string.find(cxx, "clang")) then
        add_cxflags("-Wno-error=parentheses-equality -Wno-error=missing-braces")
    end

    if is_plat("linux", "cross") then
        add_rpathdirs("$ORIGIN", "$ORIGIN/cpp")
        add_cxflags("-fvisibility=hidden", "-fvisibility-inlines-hidden")
    end

    if is_plat("macosx") then
        add_linkdirs("/usr/lib")

        -- python cannot be linked actively on macOS, so the following compile options are used
        add_shflags("-undefined dynamic_lookup", "-headerpad_max_install_names")
    end    

    add_includedirs("../hikyuu_cpp")

    -- set_policy("build.optimization.lto", true)
    add_rules("c++.unity_build", {batchsize = 0})
    add_files("./**.cpp")

    add_files("./*.cpp", "./factor/**.cpp", {unity_group="base"})
    add_files("./analysis/**.cpp", {unity_group="analysis"})
    add_files("./data_driver/**.cpp", {unity_group="data_driver"})
    add_files("./global/**.cpp", {unity_group="global"})
    add_files("./indicator/**.cpp", {unity_group="indicator"})
    add_files("./part/**.cpp", {unity_group="part"})
    add_files("./plugin/**.cpp", {unity_group="plugin"})
    add_files("./strategy/**.cpp", {unity_group="strategy"})
    add_files("./trade_manage/**.cpp", {unity_group="trade_manage"})
    add_files("./trade_sys/**.cpp", {unity_group="trade_sys"})

    on_load("windows", "linux", "macosx", function(target)
        import("lib.detect.find_tool")
        if is_plat("windows") then
            -- detect installed python3
            local python = assert(find_tool("python", {version = true}), "python not found, please install it first! note: python version must > 3.0")
            assert(python.version > "3", python.version .. " python version must > 3.0, please use python3.0 or later!")
            -- find python include and libs directory
            local pydir
            if os.getenv("CONDA_PREFIX") ~= nil then
                pydir = os.iorun("python -c \"import sys; print(sys.executable)\"")
            else
                -- using python.program directly has problems when switching within the conda environment
                pydir = os.iorunv(python.program, {"-c", "import sys; print(sys.executable)"})
            end
            pydir = path.directory(pydir)
            if pydir:endswith("Scripts") then
                -- if venv is activated, find the real python directory
                file = io.open(pydir .. "/../pyvenv.cfg", "r")
                for line in file:lines() do
                    if string.find(line, "home =") then
                        -- extract the path with the string.gmatch function
                        for path in string.gmatch(line, "home = (.*)") do
                            pydir = path
                        end
                    end
                end
                file:close()
            end            
            target:add("includedirs", pydir .. "/include")
            target:add("linkdirs", pydir .. "/libs")
            return
        end
    
        -- get python include directory.
        local pydir_include = nil;
        local pydir_lib = nil;
        if os.getenv("CONDA_PREFIX") ~= nil then
            print("CONDA_PREFIX: " .. os.getenv("CONDA_PREFIX"))
            local py3config = os.getenv("CONDA_PREFIX") .. "/bin/python3-config"
            pydir_include = os.iorun(py3config .. " --includes"):trim()
            pydir_lib = os.iorun(py3config .. " --libs"):trim()
        else
            local stmt
            if is_plat("macosx") then
                stmt = [[python -c 'import sys; v = sys.version_info; print(f"{str(v.major)}.{str(v.minor)}")']]
            else
                stmt = [[python3 -c 'import sys; v = sys.version_info; print(f"{str(v.major)}.{str(v.minor)}")']]
            end
            local python_version = os.iorun(stmt):trim()
            local py3config = "python" .. python_version .. "-config"
            -- print("py3config: " .. py3config)
            pydir_include = os.iorun(py3config .. " --includes"):trim()
            pydir_lib = os.iorun(py3config .. " --libs"):trim()
        end
        assert(pydir_include, "python3-config not found!")
        print("pydir_include: " .. pydir_include)
        -- print("pydir_lib: " .. pydir_lib)
        target:add("cxflags", pydir_include, pydir_lib)    
    end)

    after_build(function(target)
        local dst_dir = "$(projectdir)/hikyuu/cpp/"
        local dst_obj = dst_dir .. "core.so"

        if not is_plat("cross") then
          local stmt = [[python -c 'import sys; v = sys.version_info; print(str(v.major)+str(v.minor))']]
          if is_plat("linux") then
            stmt = [[python3 -c 'import sys; v = sys.version_info; print(str(v.major)+str(v.minor))']]
          end
          local python_version = os.iorun(stmt):trim()
          print("python_version: " .. python_version)
          dst_obj = dst_dir .. "core" ..  python_version
        end

        if is_plat("windows") then
            os.cp(target:targetdir() .. '/core.pyd', dst_obj .. ".pyd")
            os.cp(target:targetdir() .. '/*.dll', dst_dir)
            os.cp(target:targetdir() .. '/hikyuu.lib', dst_dir)
        elseif is_plat("macosx") then
            os.cp(target:targetdir() .. '/core.so', dst_obj .. ".so")
            os.cp(target:targetdir() .. '/*.dylib', dst_dir)
        else
            os.trycp(target:targetdir() .. '/*.so', dst_dir)
            os.trycp(target:targetdir() .. '/*.so.*', dst_dir)
            if not is_plat("cross") then
                os.trymv(dst_dir .. '/core.so', dst_obj .. ".so")
            end
        end

        if is_plat("macosx") then
            dst_obj = dst_obj .. ".so"

            -- The xmake packages ship dylibs whose install names and inter-dependencies are bare
            -- file names, which dyld can only resolve when the current working directory is this
            -- directory. Rewrite those references to @rpath and make sure each image has an
            -- @loader_path rpath, so that "import hikyuu" works from any directory. The @rpath/
            -- prefix is used because it is the shortest expansion: the prebuilt package dylibs
            -- have no spare room in their Mach-O header for a longer load command, and
            -- libhikyuu needs -headerpad_max_install_names at link time to get some.
            local lib_names = {}
            for _, filepath in ipairs(os.files(dst_dir .. "/*.dylib")) do
                lib_names[path.filename(filepath)] = true
            end

            local function imageInstallName(obj)
                local lines = {}
                for line in os.iorunv("otool", {"-D", obj}):gmatch("[^\r\n]+") do
                    table.insert(lines, line)
                end
                -- The 2nd line is the install name, sometimes suffixed with " (architecture ...)"
                local id = lines[2] and lines[2]:trim() or ""
                return id:gsub("%s*%(.+$", ""):trim()
            end

            local function fixImage(obj)
                local name = path.filename(obj)
                local id = imageInstallName(obj)
                local changed = false
                -- A bare install name can only be found in the current working directory, so make it @rpath based
                if id ~= "" and not id:find("^/") and not id:find("^@") then
                    os.run(format("install_name_tool -id @rpath/%s %s", id, obj), {try = true})
                    changed = true
                end
                for line in os.iorunv("otool", {"-L", obj}):gmatch("[^\r\n]+") do
                    local dep = line:match("^%s+([%w%.%-_/%@]+%.dylib)%s+%(")
                    local base = dep and dep:match("([^/]+%.dylib)$")
                    -- Relocate the shipped dylibs only, and leave the system libraries alone
                    if base and lib_names[base] and dep ~= name and not dep:find("^/")
                        and dep ~= "@rpath/" .. base and dep ~= "@loader_path/" .. base then
                        os.run(format("install_name_tool -change %s @rpath/%s %s", dep, base, obj), {try = true})
                        changed = true
                    end
                end
                if changed and not os.iorunv("otool", {"-l", obj}):find("LC_RPATH") then
                    os.run(format("install_name_tool -add_rpath @loader_path %s", obj), {try = true})
                end
            end

            for _, filepath in ipairs(os.files(dst_dir .. "/*.dylib")) do
                fixImage(filepath)
            end
            for _, filepath in ipairs(os.files(dst_dir .. "/core*.so")) do
                fixImage(filepath)
            end

            if get_config("mysql") and get_config("kind") ~= "shared" then
                os.cp(target:targetdir() .. '/*.a', dst_dir)
            end

            -- add the macOS signature
            local projectdir = os.projectdir() 
            local scan_dir = path.join(projectdir, "hikyuu/cpp")
            print("Start signing dynamic libraries in: " .. scan_dir)
            local ok, err = os.execv("find", {
                scan_dir,
                "-type", "f",
                "(", 
                "-name", "*.dylib", 
                "-o", 
                "-name", "*.so", 
                ")",
                "-exec", "codesign", "-s", "-", "--force", "--deep", "{}", ";"
            })
            if not ok then
                raise("Failed to sign libraries: " .. (err or "unknown error"))
            end
            print("Signing completed.")
         end

        os.cp("$(projectdir)/i18n/zh_CN/*.mo", "$(projectdir)/hikyuu/cpp/i18n/zh_CN/")
    end)


