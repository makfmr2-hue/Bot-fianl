#!/data/data/com.termux/files/usr/bin/bash

echo "Installing dependencies..."

pkg install -y python
pip install -r requirements.txt

mkdir -p $HOME/bin
cp boton $HOME/bin/boton
chmod +x $HOME/bin/boton

echo 'export PATH=$HOME/bin:$PATH' >> $HOME/.bashrc
source $HOME/.bashrc

echo "Setup complete!"
echo "Now just type: boton"