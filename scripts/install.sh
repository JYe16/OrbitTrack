# 1. 确保有 flathub remote 和 GNOME 49 runtime
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.gnome.Platform//49

# 2. 安装 bundle（把 orbittrack.flatpak 拷过去后）
flatpak install --user orbittrack.flatpak

# 3. 运行
flatpak run io.github.jye16.OrbitTrack