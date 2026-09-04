using System.Drawing.Drawing2D;
using System.Text.Json;

namespace AnimusModManager;

internal sealed class StartupSplashForm : Form
{
    private readonly string root;
    private readonly Label status = new();
    private readonly Label percent = new();
    private readonly Panel progressFill = new();
    private readonly Panel progressTrack = new();
    private Image? banner;
    private int progress;

    public event EventHandler? ManagerReady;

    public StartupSplashForm(string rootPath)
    {
        root = Path.GetFullPath(rootPath);
        Text = "Animus Mod & Outfit Manager";
        ClientSize = new Size(580, 260);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.None;
        HandleCreated += (_, _) => NativeMethods.UseSmallRoundedCorners(Handle);
        BackColor = Color.FromArgb(7, 9, 9);
        ForeColor = Color.FromArgb(231, 227, 221);
        ShowInTaskbar = true;
        DoubleBuffered = true;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
        catch { }

        var bannerPath = Path.Combine(root, "tools", "Animus_loader", "web", "assets", "amm-splash.jpg");
        if (File.Exists(bannerPath)) banner = Image.FromFile(bannerPath);

        var title = NewLabel("ANIMUS MOD & OUTFIT MANAGER", 27, 30, 500, 32, 21, Color.FromArgb(211, 179, 126));
        title.Font = new Font("Segoe UI Semibold", 16, FontStyle.Regular);
        var subtitle = NewLabel("INITIALIZING ANIMUS INTERFACE", 29, 66, 360, 20, 9, Color.FromArgb(183, 157, 116));
        subtitle.Font = new Font("Segoe UI", 8.5f, FontStyle.Regular);

        var close = NewLabel("×", 535, 12, 30, 30, 20, Color.FromArgb(205, 177, 132));
        close.TextAlign = ContentAlignment.MiddleCenter;
        close.Cursor = Cursors.Hand;
        close.Click += (_, _) => Close();
        close.MouseEnter += (_, _) => close.ForeColor = Color.White;
        close.MouseLeave += (_, _) => close.ForeColor = Color.FromArgb(205, 177, 132);

        status.SetBounds(29, 166, 465, 24);
        status.Text = "Preparing manager…";
        status.Font = new Font("Segoe UI", 10, FontStyle.Regular);
        status.ForeColor = Color.FromArgb(207, 203, 196);
        status.BackColor = Color.Transparent;

        percent.SetBounds(500, 166, 50, 24);
        percent.Text = "0%";
        percent.TextAlign = ContentAlignment.MiddleRight;
        percent.Font = new Font("Segoe UI Semibold", 9, FontStyle.Regular);
        percent.ForeColor = Color.FromArgb(211, 179, 116);
        percent.BackColor = Color.Transparent;

        progressTrack.SetBounds(29, 202, 522, 8);
        progressTrack.BackColor = Color.FromArgb(31, 31, 28);
        progressFill.SetBounds(0, 0, 0, 8);
        progressFill.BackColor = Color.FromArgb(190, 143, 65);
        progressTrack.Controls.Add(progressFill);

        var footer = NewLabel("ANIMUS SYSTEM  •  BLACK FLAG RESYNCED", 29, 224, 360, 18, 8, Color.FromArgb(117, 97, 67));
        Controls.AddRange([title, subtitle, close, status, percent, progressTrack, footer]);

        MouseDown += DragWindow;
        title.MouseDown += DragWindow;
        subtitle.MouseDown += DragWindow;
        Shown += async (_, _) => await PrepareManager();
    }

    protected override CreateParams CreateParams
    {
        get
        {
            const int dropShadow = 0x00020000;
            var parameters = base.CreateParams;
            parameters.ClassStyle |= dropShadow;
            return parameters;
        }
    }

    private static Label NewLabel(string text, int x, int y, int width, int height, float size, Color color) =>
        new()
        {
            Text = text,
            Bounds = new Rectangle(x, y, width, height),
            BackColor = Color.Transparent,
            ForeColor = color,
            Font = new Font("Segoe UI", size, FontStyle.Regular),
        };

    private void DragWindow(object? sender, MouseEventArgs eventArgs)
    {
        if (eventArgs.Button != MouseButtons.Left) return;
        NativeMethods.ReleaseCapture();
        NativeMethods.SendMessage(Handle, 0xA1, (IntPtr)2, IntPtr.Zero);
    }

    private void SetProgress(int value, string message)
    {
        progress = Math.Clamp(value, 0, 100);
        status.Text = message;
        percent.Text = $"{progress}%";
        progressFill.Width = progressTrack.ClientSize.Width * progress / 100;
        Invalidate();
    }

    private async Task PrepareManager()
    {
        try
        {
            await Task.Delay(100);
            SetProgress(12, "Locating Animus components…");

            var python = Path.Combine(root, "runtime", "python", "python.exe");
            if (!File.Exists(python))
                throw new FileNotFoundException("The bundled Animus backend runtime could not be found.", python);
            var frontend = Path.Combine(root, "tools", "Animus_loader", "web", "index.html");
            if (!File.Exists(frontend))
                throw new FileNotFoundException("The Animus interface could not be found.", frontend);

            await Task.Delay(180);
            SetProgress(64, "Portable runtime ready…");
            var (mods, outfits, texturePacks) = ReadLibraryCounts();
            await Task.Delay(120);
            SetProgress(88, $"{mods} mod package{(mods == 1 ? "" : "s")} loaded");
            await Task.Delay(130);
            SetProgress(94, $"{outfits} outfit{(outfits == 1 ? "" : "s")} and {texturePacks} other texture pack{(texturePacks == 1 ? "" : "s")} loaded");
            await Task.Delay(180);
            SetProgress(100, "Animus Mod & Outfit Manager ready");
            await Task.Delay(160);
            ManagerReady?.Invoke(this, EventArgs.Empty);
        }
        catch (Exception exception)
        {
            Program.LogFailure("Startup preloader", exception);
            progressFill.BackColor = Color.FromArgb(184, 55, 52);
            SetProgress(Math.Max(progress, 10), "Startup failed — click to view details");
            status.Cursor = Cursors.Hand;
            status.Click += (_, _) => MessageBox.Show(this, exception.Message, "Animus Mod & Outfit Manager", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private (int Mods, int Outfits, int TexturePacks) ReadLibraryCounts()
    {
        var packages = Path.Combine(root, "mods", "packages");
        var modCount = Directory.Exists(packages)
            ? Directory.EnumerateFiles(packages, "*.jmod", SearchOption.TopDirectoryOnly).Count()
            : 0;
        var outfitCount = 0;
        var texturePackCount = 0;
        var library = Path.Combine(root, "mods", "textures", "library.json");
        if (!File.Exists(library)) return (modCount, outfitCount, texturePackCount);
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(library));
            if (!document.RootElement.TryGetProperty("packs", out var packs) || packs.ValueKind != JsonValueKind.Array)
                return (modCount, outfitCount, texturePackCount);
            foreach (var pack in packs.EnumerateArray())
            {
                var category = pack.TryGetProperty("category", out var value) ? value.GetString() : "outfit";
                if (string.Equals(category, "outfit", StringComparison.OrdinalIgnoreCase)) outfitCount++;
                else texturePackCount++;
            }
        }
        catch (JsonException) { }
        catch (IOException) { }
        return (modCount, outfitCount, texturePackCount);
    }

    protected override void OnPaint(PaintEventArgs eventArgs)
    {
        base.OnPaint(eventArgs);
        var graphics = eventArgs.Graphics;
        graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
        if (banner is not null) graphics.DrawImage(banner, ClientRectangle);
        using var fade = new LinearGradientBrush(
            new Rectangle(0, 105, ClientSize.Width, 155),
            Color.FromArgb(0, 7, 9, 9),
            Color.FromArgb(220, 7, 9, 9),
            LinearGradientMode.Vertical);
        graphics.FillRectangle(fade, 0, 105, ClientSize.Width, 155);
        using var border = new Pen(Color.FromArgb(115, 153, 112, 48));
        graphics.DrawRectangle(border, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) banner?.Dispose();
        base.Dispose(disposing);
    }
}

internal sealed class StartupApplicationContext : ApplicationContext
{
    private readonly string root;
    private readonly StartupSplashForm splash;
    private MainForm? manager;

    public StartupApplicationContext(string rootPath)
    {
        root = rootPath;
        splash = new StartupSplashForm(root);
        splash.ManagerReady += OnManagerReady;
        splash.FormClosed += (_, _) =>
        {
            if (manager is null) ExitThread();
        };
        splash.Show();
    }

    private void OnManagerReady(object? sender, EventArgs eventArgs)
    {
        if (splash.IsDisposed || manager is not null) return;
        manager = new MainForm(root);
        manager.FormClosed += (_, _) => ExitThread();
        manager.Show();

        var closeSplash = new System.Windows.Forms.Timer { Interval = 900 };
        closeSplash.Tick += (_, _) =>
        {
            closeSplash.Stop();
            closeSplash.Dispose();
            if (!splash.IsDisposed) splash.Close();
        };
        closeSplash.Start();
    }
}
