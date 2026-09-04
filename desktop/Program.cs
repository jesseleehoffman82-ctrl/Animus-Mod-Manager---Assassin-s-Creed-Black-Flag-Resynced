using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace AnimusModManager;

internal sealed class LaunchOverlayForm : Form
{
    private readonly System.Windows.Forms.Timer animation = new() { Interval = 30 };
    private int frame;

    public LaunchOverlayForm(Rectangle? displayBounds = null)
    {
        FormBorderStyle = FormBorderStyle.None;
        ClientSize = new Size(278, 52);
        StartPosition = FormStartPosition.Manual;
        ShowInTaskbar = false;
        TopMost = true;
        BackColor = Color.FromArgb(8, 10, 10);
        Opacity = 0;
        DoubleBuffered = true;

        var display = displayBounds ?? Screen.PrimaryScreen?.Bounds
            ?? Screen.GetWorkingArea(Point.Empty);
        Location = new Point(display.Left + 24, display.Top + 24);

        var readyDot = new Panel
        {
            BackColor = Color.FromArgb(79, 225, 103),
            Bounds = new Rectangle(18, 23, 7, 7),
        };
        var message = new Label
        {
            Text = "MODS & OUTFITS LOADED",
            ForeColor = Color.FromArgb(229, 225, 218),
            BackColor = Color.Transparent,
            Font = new Font("Segoe UI Semibold", 10.5f),
            Bounds = new Rectangle(37, 14, 224, 25),
        };
        Controls.AddRange([readyDot, message]);

        animation.Tick += (_, _) =>
        {
            frame++;
            if (frame <= 9) Opacity = Math.Min(.96, frame / 9.0 * .96);
            else if (frame >= 78) Opacity = Math.Max(0, (92 - frame) / 14.0 * .96);
            if (frame >= 92)
            {
                animation.Stop();
                Close();
            }
        };
        Shown += (_, _) => animation.Start();
    }

    protected override bool ShowWithoutActivation => true;

    protected override CreateParams CreateParams
    {
        get
        {
            const int wsExNoActivate = 0x08000000;
            const int wsExToolWindow = 0x00000080;
            const int wsExTransparent = 0x00000020;
            var parameters = base.CreateParams;
            parameters.ExStyle |= wsExNoActivate | wsExToolWindow | wsExTransparent;
            return parameters;
        }
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        base.OnPaint(eventArgs);
        using var border = new Pen(Color.FromArgb(155, 160, 115, 48));
        eventArgs.Graphics.DrawRectangle(border, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
        using var accent = new Pen(Color.FromArgb(195, 184, 139, 65), 2);
        eventArgs.Graphics.DrawLine(accent, 0, 0, 72, 0);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) animation.Dispose();
        base.Dispose(disposing);
    }
}

internal sealed class ConflictPromptForm : Form
{
    private static readonly Color Surface = Color.FromArgb(9, 11, 11);
    private static readonly Color SurfaceRaised = Color.FromArgb(16, 18, 18);
    private static readonly Color Gold = Color.FromArgb(183, 139, 70);
    private static readonly Color GoldBright = Color.FromArgb(224, 188, 116);
    private static readonly Color TextPrimary = Color.FromArgb(232, 229, 222);
    private static readonly Color TextMuted = Color.FromArgb(168, 166, 160);

    public ConflictPromptForm(string packName, string itemLabel, string action,
                              IEnumerable<string?> conflictNames)
    {
        var names = conflictNames.Where(name => !string.IsNullOrWhiteSpace(name))
            .Select(name => name!).ToArray();
        if (names.Length == 0) names = ["Another enabled texture pack"];

        FormBorderStyle = FormBorderStyle.None;
        HandleCreated += (_, _) => NativeMethods.UseSmallRoundedCorners(Handle);
        StartPosition = FormStartPosition.CenterParent;
        ShowInTaskbar = false;
        BackColor = Surface;
        ForeColor = TextPrimary;
        ClientSize = new Size(570, Math.Clamp(306 + names.Length * 27, 350, 470));
        MinimumSize = ClientSize;
        MaximumSize = ClientSize;
        AutoScaleMode = AutoScaleMode.Dpi;
        DoubleBuffered = true;

        var header = new Panel
        {
            BackColor = SurfaceRaised,
            Bounds = new Rectangle(1, 1, ClientSize.Width - 2, 49),
            Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
        };
        var title = new Label
        {
            Text = itemLabel == "outfit" ? "SHARED OUTFIT SLOT"
                : itemLabel == "sail design" ? "SHARED SAIL SLOT" : "SHARED TEXTURE SLOT",
            ForeColor = GoldBright,
            BackColor = Color.Transparent,
            Font = new Font("Segoe UI Semibold", 10.5f),
            Bounds = new Rectangle(23, 15, 400, 24),
        };
        var close = MakeButton("×", 42);
        close.Font = new Font("Segoe UI", 13f);
        close.Bounds = new Rectangle(ClientSize.Width - 47, 7, 34, 34);
        close.Anchor = AnchorStyles.Top | AnchorStyles.Right;
        close.DialogResult = DialogResult.No;
        header.Controls.AddRange([title, close]);

        var warning = new Label
        {
            Text = "!",
            TextAlign = ContentAlignment.MiddleCenter,
            ForeColor = GoldBright,
            BackColor = Color.FromArgb(29, 25, 17),
            Font = new Font("Segoe UI Semibold", 13f),
            Bounds = new Rectangle(24, 73, 30, 30),
        };
        var intro = new Label
        {
            Text = $"“{packName}” uses the same vanilla {itemLabel} slot as:",
            ForeColor = TextPrimary,
            BackColor = Color.Transparent,
            Font = new Font("Segoe UI", 10f),
            AutoEllipsis = true,
            Bounds = new Rectangle(69, 76, ClientSize.Width - 94, 25),
            Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
        };

        var listPanel = new Panel
        {
            BackColor = Color.FromArgb(6, 8, 8),
            Bounds = new Rectangle(24, 119, ClientSize.Width - 48,
                Math.Min(132, Math.Max(58, names.Length * 27 + 12))),
            Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
            AutoScroll = true,
        };
        for (var index = 0; index < names.Length; index++)
        {
            listPanel.Controls.Add(new Label
            {
                Text = $"◆  {names[index]}",
                ForeColor = index == 0 ? GoldBright : TextPrimary,
                BackColor = Color.Transparent,
                Font = new Font("Segoe UI", 9.5f),
                AutoEllipsis = true,
                Bounds = new Rectangle(16, 8 + index * 27, listPanel.ClientSize.Width - 32, 22),
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
            });
        }

        var questionTop = listPanel.Bottom + 18;
        var pluralLabel = itemLabel == "outfit" ? "outfits"
            : itemLabel == "weapon skin" ? "weapon skins"
            : itemLabel == "sail design" ? "sail designs"
            : itemLabel == "texture mod" ? "texture mods" : "crew textures";
        var question = new Label
        {
            Text = $"Disable all listed {pluralLabel} and {action} “{packName}” instead?",
            ForeColor = TextMuted,
            BackColor = Color.Transparent,
            Font = new Font("Segoe UI", 9.5f),
            AutoEllipsis = true,
            Bounds = new Rectangle(24, questionTop, ClientSize.Width - 48, 28),
            Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
        };

        var cancel = MakeButton("CANCEL", 105);
        cancel.Bounds = new Rectangle(ClientSize.Width - 292, ClientSize.Height - 61, 105, 36);
        cancel.Anchor = AnchorStyles.Bottom | AnchorStyles.Right;
        cancel.DialogResult = DialogResult.No;
        var confirm = MakeButton("DISABLE & CONTINUE", 153, true);
        confirm.Bounds = new Rectangle(ClientSize.Width - 177, ClientSize.Height - 61, 153, 36);
        confirm.Anchor = AnchorStyles.Bottom | AnchorStyles.Right;
        confirm.DialogResult = DialogResult.Yes;

        AcceptButton = confirm;
        CancelButton = cancel;
        Controls.AddRange([header, warning, intro, listPanel, question, cancel, confirm]);
    }

    private static Button MakeButton(string text, int width, bool accented = false)
    {
        var button = new Button
        {
            Text = text,
            Size = new Size(width, 36),
            FlatStyle = FlatStyle.Flat,
            BackColor = accented ? Color.FromArgb(33, 28, 18) : SurfaceRaised,
            ForeColor = accented ? GoldBright : TextPrimary,
            Font = new Font("Segoe UI Semibold", 8.5f),
            Cursor = Cursors.Hand,
            TabStop = true,
        };
        button.FlatAppearance.BorderColor = accented ? Gold : Color.FromArgb(75, 70, 58);
        button.FlatAppearance.BorderSize = 1;
        button.FlatAppearance.MouseOverBackColor = Color.FromArgb(40, 34, 22);
        button.FlatAppearance.MouseDownBackColor = Color.FromArgb(48, 38, 21);
        return button;
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        base.OnPaint(eventArgs);
        using var border = new Pen(Color.FromArgb(180, Gold));
        eventArgs.Graphics.DrawRectangle(border, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
        using var accent = new Pen(GoldBright, 2);
        eventArgs.Graphics.DrawLine(accent, 0, 0, 115, 0);
    }
}

internal sealed class SailTargetPromptForm : Form
{
    private sealed record TargetChoice(string Id, string Name, string Kind)
    {
        public override string ToString() => Kind == "emblem"
            ? $"ADVANCED — {Name}" : Name;
    }

    private static readonly Color Surface = Color.FromArgb(9, 11, 11);
    private static readonly Color Raised = Color.FromArgb(16, 18, 18);
    private static readonly Color Gold = Color.FromArgb(183, 139, 70);
    private static readonly Color GoldBright = Color.FromArgb(224, 188, 116);
    private static readonly Color TextPrimary = Color.FromArgb(232, 229, 222);
    private readonly ComboBox targets = new();

    public string? SelectedTargetId => (targets.SelectedItem as TargetChoice)?.Id;

    public SailTargetPromptForm(JsonArray options, string defaultId)
    {
        FormBorderStyle = FormBorderStyle.None;
        HandleCreated += (_, _) => NativeMethods.UseSmallRoundedCorners(Handle);
        StartPosition = FormStartPosition.CenterParent;
        ShowInTaskbar = false;
        BackColor = Surface;
        ForeColor = TextPrimary;
        ClientSize = new Size(570, 270);
        MinimumSize = ClientSize;
        MaximumSize = ClientSize;
        AutoScaleMode = AutoScaleMode.Dpi;

        var header = new Panel
        {
            BackColor = Raised,
            Bounds = new Rectangle(1, 1, ClientSize.Width - 2, 49),
        };
        header.MouseDown += (_, e) =>
        {
            if (e.Button != MouseButtons.Left) return;
            NativeMethods.ReleaseCapture();
            NativeMethods.SendMessage(Handle, 0xA1, (IntPtr)0x2, IntPtr.Zero);
        };
        header.Controls.Add(new Label
        {
            Text = "CHOOSE VANILLA SAIL SET",
            ForeColor = GoldBright,
            BackColor = Color.Transparent,
            Font = new Font("Segoe UI Semibold", 10.5f),
            Bounds = new Rectangle(23, 15, 400, 24),
        });

        var close = MakeButton("×", 34);
        close.Font = new Font("Segoe UI", 13f);
        close.Bounds = new Rectangle(ClientSize.Width - 47, 7, 34, 34);
        close.DialogResult = DialogResult.Cancel;
        header.Controls.Add(close);

        Controls.Add(new Label
        {
            Text = "Select the in-game sail cosmetic this design will replace.",
            ForeColor = TextPrimary,
            BackColor = Color.Transparent,
            Font = new Font("Segoe UI", 10f),
            Bounds = new Rectangle(24, 72, ClientSize.Width - 48, 25),
        });
        Controls.Add(new Label
        {
            Text = "Different targets can remain enabled together. The manager warns when two designs share one target.",
            ForeColor = Color.FromArgb(168, 166, 160),
            BackColor = Color.Transparent,
            Font = new Font("Segoe UI", 9f),
            Bounds = new Rectangle(24, 99, ClientSize.Width - 48, 40),
        });

        targets.Bounds = new Rectangle(24, 145, ClientSize.Width - 48, 34);
        targets.DropDownStyle = ComboBoxStyle.DropDownList;
        targets.FlatStyle = FlatStyle.Flat;
        targets.BackColor = Raised;
        targets.ForeColor = TextPrimary;
        targets.Font = new Font("Segoe UI", 9.5f);
        targets.DrawMode = DrawMode.OwnerDrawFixed;
        targets.ItemHeight = 25;
        targets.DrawItem += (_, e) =>
        {
            if (e.Index < 0) return;
            e.DrawBackground();
            using var brush = new SolidBrush((e.State & DrawItemState.Selected) != 0
                ? GoldBright : TextPrimary);
            e.Graphics.DrawString(targets.Items[e.Index]?.ToString(), targets.Font,
                brush, e.Bounds.Left + 6, e.Bounds.Top + 4);
        };
        foreach (var node in options)
        {
            if (node is not JsonObject item) continue;
            var id = item["id"]?.GetValue<string>() ?? "";
            var name = item["name"]?.GetValue<string>() ?? id;
            var kind = item["kind"]?.GetValue<string>() ?? "sail-set";
            var choice = new TargetChoice(id, name, kind);
            targets.Items.Add(choice);
            if (id == defaultId) targets.SelectedItem = choice;
        }
        if (targets.SelectedIndex < 0 && targets.Items.Count > 0) targets.SelectedIndex = 0;

        var cancel = MakeButton("CANCEL", 105);
        cancel.Bounds = new Rectangle(ClientSize.Width - 292, ClientSize.Height - 61, 105, 36);
        cancel.DialogResult = DialogResult.Cancel;
        var confirm = MakeButton("USE THIS SAIL SET", 153, true);
        confirm.Bounds = new Rectangle(ClientSize.Width - 177, ClientSize.Height - 61, 153, 36);
        confirm.DialogResult = DialogResult.OK;
        AcceptButton = confirm;
        CancelButton = cancel;
        Controls.AddRange([header, targets, cancel, confirm]);
    }

    private static Button MakeButton(string text, int width, bool accented = false)
    {
        var button = new Button
        {
            Text = text,
            Size = new Size(width, 36),
            FlatStyle = FlatStyle.Flat,
            BackColor = accented ? Color.FromArgb(33, 28, 18) : Raised,
            ForeColor = accented ? GoldBright : TextPrimary,
            Font = new Font("Segoe UI Semibold", 8.5f),
            Cursor = Cursors.Hand,
        };
        button.FlatAppearance.BorderColor = accented ? Gold : Color.FromArgb(75, 70, 58);
        return button;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        using var border = new Pen(Color.FromArgb(180, Gold));
        e.Graphics.DrawRectangle(border, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
    }
}

internal sealed class MainForm : Form
{
    private const int WmNcHitTest = 0x0084;
    private const int HtClient = 1;
    private const int HtLeft = 10;
    private const int HtRight = 11;
    private const int HtTop = 12;
    private const int HtTopLeft = 13;
    private const int HtTopRight = 14;
    private const int HtBottom = 15;
    private const int HtBottomLeft = 16;
    private const int HtBottomRight = 17;
    private const int ResizeBorder = 9;

    private readonly string root;
    private readonly WebView2 webView = new() { Dock = DockStyle.Fill };

    public MainForm(string rootPath)
    {
        root = Path.GetFullPath(rootPath);
        Text = "Animus Mod & Outfit Manager";
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
        catch { /* The executable icon is cosmetic; startup should still continue. */ }
        BackColor = Color.FromArgb(7, 8, 8);
        Padding = System.Windows.Forms.Padding.Empty;
        SetStyle(ControlStyles.ResizeRedraw, true);
        webView.DefaultBackgroundColor = Color.FromArgb(7, 8, 8);
        ClientSize = new Size(1000, 640);
        MinimumSize = new Size(860, 560);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.None;
        HandleCreated += (_, _) => NativeMethods.UseSmallRoundedCorners(Handle);
        Controls.Add(webView);
        Shown += async (_, _) =>
        {
            try { await InitializeWebView(); }
            catch (Exception ex)
            {
                Program.LogFailure("WebView initialization", ex);
                MessageBox.Show(this, ex.Message, "Animus Mod & Outfit Manager could not start",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                Close();
            }
        };
    }

    private async Task InitializeWebView()
    {
        var dataFolder = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AnimusModManager", "WebView2");
        var environment = await CoreWebView2Environment.CreateAsync(null, dataFolder);
        await webView.EnsureCoreWebView2Async(environment);
        var core = webView.CoreWebView2;
        // The frontend is loaded from local project files and is updated in
        // place. Never let WebView2 retain an older app.js/app.css between
        // manager restarts.
        try
        {
            await core.CallDevToolsProtocolMethodAsync(
                "Network.setCacheDisabled", "{\"cacheDisabled\":true}");
        }
        catch { /* Asset query versions below remain the fallback. */ }
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.IsStatusBarEnabled = false;
        core.WebMessageReceived += OnWebMessage;
        core.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true });
        };
        var indexPath = Path.Combine(root, "tools", "Animus_loader", "web", "index.html");
        if (!File.Exists(indexPath))
            throw new FileNotFoundException("The Animus interface could not be found.", indexPath);
        core.NavigationCompleted += (_, e) =>
        {
            if (!e.IsSuccess)
            {
                var error = new InvalidOperationException($"Interface navigation failed: {e.WebErrorStatus}");
                Program.LogFailure("Frontend navigation", error);
                core.NavigateToString($"<body style='background:#080909;color:#eee;font:16px Segoe UI;padding:30px'><h2>Animus Mod &amp; Outfit Manager</h2><p>{System.Net.WebUtility.HtmlEncode(error.Message)}</p><p>{System.Net.WebUtility.HtmlEncode(indexPath)}</p></body>");
            }
        };
        core.Navigate(new Uri(indexPath).AbsoluteUri);
    }

    private async void OnWebMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        string id = "";
        try
        {
            using var request = JsonDocument.Parse(e.WebMessageAsJson);
            var requestRoot = request.RootElement;
            id = requestRoot.GetProperty("id").GetString() ?? "";
            var method = requestRoot.GetProperty("method").GetString() ?? "";
            var args = requestRoot.TryGetProperty("args", out var argsNode)
                ? argsNode.Clone()
                : JsonDocument.Parse("[]").RootElement.Clone();

            if (HandleWindowCommand(method))
            {
                await PostResponse(id, new JsonObject { ["result"] = true });
                return;
            }

            string rpcMethod = method;
            JsonArray rpcArgs = JsonNode.Parse(args.GetRawText())?.AsArray() ?? [];
            var showLaunchOverlay = false;
            if (method == "open_nexus_page")
            {
                Process.Start(new ProcessStartInfo("https://www.nexusmods.com/assassinscreedblackflagresynced/mods/")
                {
                    UseShellExecute = true,
                });
                await PostResponse(id, new JsonObject { ["result"] = true });
                return;
            }
            if (method == "browse_game_dir")
            {
                using var dialog = new FolderBrowserDialog
                {
                    Description = "Select the Assassin's Creed Black Flag Resynced game folder",
                    ShowNewFolderButton = false,
                    UseDescriptionForTitle = true,
                };
                if (dialog.ShowDialog(this) != DialogResult.OK)
                {
                    await PostResponse(id, new JsonObject { ["result"] = null });
                    return;
                }
                rpcMethod = "set_game_dir";
                rpcArgs = [dialog.SelectedPath];
            }
            else if (method == "install_mod")
            {
                using var dialog = new OpenFileDialog
                {
                    Title = "Select an Animus or Nexus mod archive",
                    Filter = "All files (*.*)|*.*",
                    Multiselect = false,
                };
                if (dialog.ShowDialog(this) != DialogResult.OK)
                {
                    await PostResponse(id, new JsonObject { ["result"] = null });
                    return;
                }
                rpcMethod = "install_mod_path";
                rpcArgs = [dialog.FileName];
            }
            else if (method == "install_pack")
            {
                var category = rpcArgs.Count > 0 ? rpcArgs[0]?.GetValue<string>() ?? "outfit" : "outfit";
                using var dialog = new OpenFileDialog
                {
                    Title = "Select an outfit, weapon, crew, or sail texture pack",
                    Filter = "All files (*.*)|*.*",
                    Multiselect = false,
                };
                if (dialog.ShowDialog(this) != DialogResult.OK)
                {
                    await PostResponse(id, new JsonObject { ["result"] = null });
                    return;
                }
                if (category == "sail")
                {
                    var choicesPayload = await RunPython("get_sail_targets", []);
                    if (choicesPayload["error"] is not null)
                        throw new InvalidOperationException(
                            choicesPayload["error"]?.GetValue<string>() ?? "Could not load sail targets");
                    var choicesResult = choicesPayload["result"] as JsonObject
                        ?? throw new InvalidOperationException("The sail target catalogue is unavailable.");
                    var choices = choicesResult["targets"] as JsonArray ?? [];
                    var defaultId = choicesResult["default_id"]?.GetValue<string>() ?? "common";
                    using var targetPrompt = new SailTargetPromptForm(choices, defaultId);
                    if (targetPrompt.ShowDialog(this) != DialogResult.OK ||
                        string.IsNullOrWhiteSpace(targetPrompt.SelectedTargetId))
                    {
                        await PostResponse(id, new JsonObject { ["result"] = null });
                        return;
                    }
                    rpcArgs = [category, dialog.FileName, targetPrompt.SelectedTargetId];
                }
                await PostJson(new JsonObject
                {
                    ["event"] = "install_progress",
                    ["category"] = category,
                    ["stage"] = "installing"
                }.ToJsonString());
                rpcMethod = "install_pack_path";
                if (category != "sail") rpcArgs = [category, dialog.FileName];
            }
            else if (method == "update_item")
            {
                var itemType = rpcArgs.Count > 0 ? rpcArgs[0]?.GetValue<string>() ?? "mod" : "mod";
                var itemId = rpcArgs.Count > 1 ? rpcArgs[1]?.GetValue<string>() ?? "" : "";
                var isMod = itemType == "mod";
                using var dialog = new OpenFileDialog
                {
                    Title = isMod ? "Select the replacement mod archive" : "Select the replacement texture pack",
                    Filter = "All files (*.*)|*.*",
                    Multiselect = false,
                };
                if (dialog.ShowDialog(this) != DialogResult.OK)
                {
                    await PostResponse(id, new JsonObject { ["result"] = null });
                    return;
                }
                rpcMethod = isMod ? "update_mod_path" : "update_pack_path";
                rpcArgs = isMod
                    ? [itemId, dialog.FileName]
                    : [itemType, itemId, dialog.FileName];
            }
            else if (method == "launch_game")
            {
                var statePayload = await RunPython("get_state", []);
                showLaunchOverlay = statePayload["error"] is null;
            }

            var payload = await RunPython(rpcMethod, rpcArgs);
            if ((method == "install_pack" || method == "install_mod" || method == "toggle_pack") && payload["error"] is null &&
                payload["result"] is JsonObject installResult &&
                installResult["requires_confirmation"]?.GetValue<bool>() == true)
            {
                var category = installResult["category"]?.GetValue<string>() ?? "outfit";
                var packId = installResult["pack_id"]?.GetValue<string>() ?? "";
                var packName = installResult["pack_name"]?.GetValue<string>() ?? "This outfit";
                var pendingAction = installResult["pending_action"]?.GetValue<string>() ?? "enable";
                var conflicts = installResult["conflicts"] as JsonArray ?? [];
                var conflictNames = conflicts
                    .Select(item => item?["name"]?.GetValue<string>())
                    .Where(name => !string.IsNullOrWhiteSpace(name))
                    .ToArray();
                var itemLabel = category == "outfit" ? "outfit"
                    : category == "weapon" ? "weapon skin"
                    : category == "crew" ? "crew texture"
                    : category == "sail" ? "sail design" : "texture mod";
                using var prompt = new ConflictPromptForm(
                    packName,
                    itemLabel,
                    pendingAction == "install" ? "install" : "enable",
                    conflictNames);
                var answer = prompt.ShowDialog(this);
                payload = answer == DialogResult.Yes
                    ? await RunPython("resolve_pack_conflict", [category, packId, pendingAction])
                    : pendingAction == "install"
                        ? await RunPython("cancel_pack_install", [packId])
                        : await RunPython("cancel_pack_enable", [packId]);
            }
            payload["id"] = id;
            await PostJson(payload.ToJsonString());
            if (showLaunchOverlay && payload["error"] is null)
                _ = ShowLaunchOverlayWhenGameStarts();
        }
        catch (Exception ex)
        {
            await PostResponse(id, new JsonObject { ["error"] = ex.Message });
        }
    }

    private static int CountEnabled(JsonObject? state, string key)
    {
        if (state?[key] is not JsonArray rows) return 0;
        return rows.Count(row => row?["enabled"]?.GetValue<bool>() == true);
    }

    private async Task ShowLaunchOverlayWhenGameStarts()
    {
        Rectangle? display = null;
        var gameWindow = IntPtr.Zero;
        for (var attempt = 0; attempt < 90; attempt++)
        {
            foreach (var process in Process.GetProcessesByName("ACBlackFlag"))
            {
                using (process)
                {
                    process.Refresh();
                    if (process.MainWindowHandle == IntPtr.Zero) continue;
                    gameWindow = process.MainWindowHandle;
                    display = Screen.FromHandle(gameWindow).Bounds;
                    break;
                }
            }
            if (display is not null) break;
            await Task.Delay(500);
        }

        if (IsDisposed) return;
        if (gameWindow != IntPtr.Zero)
        {
            // Do not alter, resize, foreground, or re-style the game window.
            // Steam owns the launch and its input session; manipulating the
            // window here can disturb controller/Steam Input initialization.
            WindowState = FormWindowState.Minimized;
            // Give the game ten seconds to finish its startup transition and
            // begin rendering before the loaded-mod confirmation is shown.
            await Task.Delay(10_000);
        }

        if (IsDisposed) return;
        var overlay = new LaunchOverlayForm(display);
        overlay.Show();
        overlay.BringToFront();
    }

    private bool HandleWindowCommand(string method)
    {
        switch (method)
        {
            case "win_minimize": WindowState = FormWindowState.Minimized; return true;
            case "win_toggle_maximize":
                WindowState = WindowState == FormWindowState.Maximized
                    ? FormWindowState.Normal : FormWindowState.Maximized;
                return true;
            case "win_restore": WindowState = FormWindowState.Normal; return true;
            case "win_close": Close(); return true;
            case "win_drag":
                NativeMethods.ReleaseCapture();
                NativeMethods.SendMessage(Handle, 0xA1, (IntPtr)0x2, IntPtr.Zero);
                return true;
            case "win_resize_left": return BeginResize(HtLeft);
            case "win_resize_right": return BeginResize(HtRight);
            case "win_resize_top": return BeginResize(HtTop);
            case "win_resize_top_left": return BeginResize(HtTopLeft);
            case "win_resize_top_right": return BeginResize(HtTopRight);
            case "win_resize_bottom": return BeginResize(HtBottom);
            case "win_resize_bottom_left": return BeginResize(HtBottomLeft);
            case "win_resize_bottom_right": return BeginResize(HtBottomRight);
            default: return false;
        }
    }

    private bool BeginResize(int hitTest)
    {
        if (WindowState != FormWindowState.Normal) return true;
        NativeMethods.ReleaseCapture();
        NativeMethods.SendMessage(Handle, 0xA1, (IntPtr)hitTest, IntPtr.Zero);
        return true;
    }

    private async Task<JsonObject> RunPython(string method, JsonArray args)
    {
        var bundledPython = Path.Combine(root, "runtime", "python", "python.exe");
        var start = new ProcessStartInfo
        {
            FileName = File.Exists(bundledPython) ? bundledPython : "python",
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        start.ArgumentList.Add("-m");
        start.ArgumentList.Add("Animus_loader.desktop_rpc");
        start.Environment["PYTHONPATH"] = Path.Combine(root, "tools");
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Could not start Python backend");
        var request = new JsonObject { ["method"] = method, ["args"] = args };
        await process.StandardInput.WriteAsync(request.ToJsonString());
        process.StandardInput.Close();
        var outputTask = process.StandardOutput.ReadToEndAsync();
        var errorTask = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        var output = await outputTask;
        var error = await errorTask;
        if (process.ExitCode != 0 || string.IsNullOrWhiteSpace(output))
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(error) ? "Python backend failed" : error.Trim());
        return JsonNode.Parse(output)?.AsObject() ?? throw new InvalidOperationException("Invalid backend response");
    }

    private Task PostResponse(string id, JsonObject payload)
    {
        payload["id"] = id;
        return PostJson(payload.ToJsonString());
    }

    private Task PostJson(string json)
    {
        if (IsDisposed || webView.CoreWebView2 is null) return Task.CompletedTask;
        webView.CoreWebView2.PostWebMessageAsJson(json);
        return Task.CompletedTask;
    }

    protected override void WndProc(ref Message message)
    {
        base.WndProc(ref message);
        if (message.Msg != WmNcHitTest || (int)message.Result != HtClient ||
            WindowState == FormWindowState.Maximized)
            return;

        var screenPoint = new Point(
            unchecked((short)(long)message.LParam),
            unchecked((short)((long)message.LParam >> 16)));
        var point = PointToClient(screenPoint);
        var left = point.X <= ResizeBorder;
        var right = point.X >= ClientSize.Width - ResizeBorder;
        var top = point.Y <= ResizeBorder;
        var bottom = point.Y >= ClientSize.Height - ResizeBorder;

        message.Result = (IntPtr)(
            top && left ? HtTopLeft :
            top && right ? HtTopRight :
            bottom && left ? HtBottomLeft :
            bottom && right ? HtBottomRight :
            left ? HtLeft :
            right ? HtRight :
            top ? HtTop :
            bottom ? HtBottom :
            HtClient);
    }
}

internal static class NativeMethods
{
    internal const int GwlStyle = -16;
    internal const int WsCaption = 0x00C00000;
    internal const int WsThickFrame = 0x00040000;
    internal const int WsMinimizeBox = 0x00020000;
    internal const int WsMaximizeBox = 0x00010000;
    internal const int WsSysMenu = 0x00080000;
    internal const uint SwpFrameChanged = 0x0020;
    internal const uint SwpShowWindow = 0x0040;
    internal const int SwShow = 5;

    [DllImport("user32.dll")] internal static extern bool ReleaseCapture();
    [DllImport("user32.dll")] internal static extern IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", SetLastError = true)] internal static extern int GetWindowLong(IntPtr hWnd, int index);
    [DllImport("user32.dll", SetLastError = true)] internal static extern int SetWindowLong(IntPtr hWnd, int index, int newLong);
    [DllImport("user32.dll", SetLastError = true)] internal static extern bool SetWindowPos(IntPtr hWnd, IntPtr insertAfter, int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll")] internal static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr hWnd, int command);
    [DllImport("dwmapi.dll")] private static extern int DwmSetWindowAttribute(
        IntPtr hWnd, int attribute, ref int value, int valueSize);

    internal static void UseSmallRoundedCorners(IntPtr handle)
    {
        // DWMWA_WINDOW_CORNER_PREFERENCE is available on Windows 11. Older
        // Windows versions simply retain their normal square window shape.
        if (!OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000)) return;
        const int cornerPreferenceAttribute = 33;
        const int roundSmall = 3;
        var preference = roundSmall;
        _ = DwmSetWindowAttribute(handle, cornerPreferenceAttribute,
            ref preference, sizeof(int));
    }
}

internal static class Program
{
    private static string? logPath;

    internal static void LogFailure(string context, Exception exception)
    {
        if (logPath is null) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
            File.AppendAllText(logPath,
                $"{DateTime.Now:O} {context}\r\n{exception}\r\n\r\n");
        }
        catch { }
    }

    private static bool HasFrontend(string path) =>
        File.Exists(Path.Combine(path, "tools", "Animus_loader", "web", "index.html"));

    private static string ResolveRoot(string[] args)
    {
        var candidates = new List<string>();
        if (args.Length > 0 && !string.IsNullOrWhiteSpace(args[0]))
            candidates.Add(args[0]);
        candidates.Add(Directory.GetCurrentDirectory());

        var cursor = new DirectoryInfo(AppContext.BaseDirectory);
        for (var depth = 0; cursor is not null && depth < 10; depth++, cursor = cursor.Parent)
            candidates.Add(cursor.FullName);

        foreach (var candidate in candidates)
        {
            try
            {
                var fullPath = Path.GetFullPath(candidate.Trim().Trim('"'));
                if (HasFrontend(fullPath)) return fullPath;
            }
            catch { }
        }

        throw new DirectoryNotFoundException(
            "The Animus interface folder could not be located. Extract the complete package and run AnimusModManager.exe.");
    }

    [STAThread]
    private static void Main(string[] args)
    {
        string root;
        try { root = ResolveRoot(args); }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Animus Mod & Outfit Manager could not start",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        logPath = Path.Combine(root, "mods", "animus-native-shell.log");
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (_, e) => LogFailure("UI thread", e.Exception);
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
            LogFailure("Unhandled runtime failure", e.ExceptionObject as Exception ?? new Exception(e.ExceptionObject?.ToString()));
        try
        {
            ApplicationConfiguration.Initialize();
            Application.Run(new StartupApplicationContext(root));
        }
        catch (Exception ex)
        {
            LogFailure("Native application startup", ex);
            MessageBox.Show(ex.Message, "Animus Mod & Outfit Manager could not start",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
