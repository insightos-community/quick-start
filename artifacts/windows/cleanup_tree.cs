// Offline cleanup without PowerShell per-file overhead or MAX_PATH dependence.
using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class SemanticCleanupTree {
    const uint Missing = 0xffffffff, Directory = 0x10, Reparse = 0x400;
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    struct FindData {
        public uint Attributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME Created, Accessed, Written;
        public uint SizeHigh, SizeLow, Reserved0, Reserved1;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=260)] public string Name;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=14)] public string AlternateName;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern uint GetFileAttributesW(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr FindFirstFileW(string path, out FindData data);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool FindNextFileW(IntPtr find, out FindData data);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool FindClose(IntPtr find);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool DeleteFileW(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool RemoveDirectoryW(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool SetFileAttributesW(string path, uint attributes);

    static string Native(string path) {
        if (path.StartsWith(@"\\?\")) return path;
        if (path.StartsWith(@"\\")) return @"\\?\UNC\" + path.Substring(2);
        return @"\\?\" + path;
    }
    static uint Attributes(string path) {
        uint value = GetFileAttributesW(Native(path));
        if (value == Missing) {
            int error = Marshal.GetLastWin32Error();
            if (error != 2 && error != 3) throw new Win32Exception(error, path);
        }
        return value;
    }
    static void Plain(string path) {
        int rootLength;
        if (path.Length >= 3 && path[1] == ':' && path[2] == '\\') rootLength = 3;
        else if (path.StartsWith(@"\\") && !path.StartsWith(@"\\?\")) {
            int server = path.IndexOf('\\', 2);
            if (server < 0) throw new ArgumentException("Expected a share path");
            int share = path.IndexOf('\\', server+1);
            rootLength = share < 0 ? path.Length : share;
        } else throw new ArgumentException("Expected an absolute installation path");
        while (path.Length >= rootLength) {
            uint value = Attributes(path);
            if (value != Missing && (value & Reparse) != 0) throw new InvalidOperationException("Reparse point: "+path);
            if (path.Length == rootLength) break;
            path = path.Substring(0, Math.Max(rootLength, path.LastIndexOf('\\')));
        }
    }
    static IEnumerable<string> Children(string path) {
        FindData data;
        IntPtr handle = FindFirstFileW(Native(path)+@"\*", out data);
        if (handle == new IntPtr(-1)) {
            int error = Marshal.GetLastWin32Error();
            if (error == 2) yield break;
            throw new Win32Exception(error, path);
        }
        try {
            do {
                if (data.Name != "." && data.Name != "..") yield return path+@"\"+data.Name;
            } while (FindNextFileW(handle, out data));
            int error = Marshal.GetLastWin32Error();
            if (error != 18) throw new Win32Exception(error, path);
        } finally { FindClose(handle); }
    }
    public static void Check(string path) {
        Plain(path);
        uint value = Attributes(path);
        if (value != Missing && (value & Directory) != 0)
            foreach (string child in Children(path)) Check(child);
    }
    public static void Remove(string path) {
        Plain(path); // Recheck ancestors and links during deletion, after preflight.
        uint value = Attributes(path);
        if (value == Missing) return;
        if ((value & Directory) != 0) {
            foreach (string child in Children(path)) Remove(child);
            if (!RemoveDirectoryW(Native(path))) throw new Win32Exception(Marshal.GetLastWin32Error(), path);
        } else {
            if (!SetFileAttributesW(Native(path), 0x80) || !DeleteFileW(Native(path)))
                throw new Win32Exception(Marshal.GetLastWin32Error(), path);
        }
    }
}
