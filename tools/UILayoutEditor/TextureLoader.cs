using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
namespace HalkUIEditor {
    public static class TextureLoader {
        static uint U32(byte[] b,int i){if(i<0||i+4>b.Length)throw new InvalidDataException("DDS обрезан.");return (uint)(b[i]|b[i+1]<<8|b[i+2]<<16|b[i+3]<<24);}
        static int Rgb565(int c){int r=(c>>11)&31,g=(c>>5)&63,b=c&31;return (((r<<3)|(r>>2))<<16)|(((g<<2)|(g>>4))<<8)|((b<<3)|(b>>2));}
        static int Mix(int a,int b,int wa,int wb,int div){return (((((a>>16)&255)*wa+((b>>16)&255)*wb)/div)<<16)|(((((a>>8)&255)*wa+((b>>8)&255)*wb)/div)<<8)|(((a&255)*wa+(b&255)*wb)/div);}
        static int Channel(uint p,uint mask,int defaultValue){if(mask==0)return defaultValue;int shift=0;while((mask&1)==0){mask>>=1;p>>=1;shift++;}return (int)((p&mask)*255UL/mask);}
        public static Bitmap Load(string path){if(!Path.GetExtension(path).Equals(".dds",StringComparison.OrdinalIgnoreCase)){using(var im=System.Drawing.Image.FromFile(path))return new Bitmap(im);}return Decode(File.ReadAllBytes(path));}
        public static Bitmap Decode(byte[] b){
            if(b.Length<128||U32(b,0)!=0x20534444||U32(b,4)!=124||U32(b,76)!=32)throw new InvalidDataException("Некорректный заголовок DDS.");
            int w=(int)U32(b,16),h=(int)U32(b,12);if(w<1||h<1||w>8192||h>8192||(long)w*h>33554432)throw new InvalidDataException("Размер DDS не поддерживается (до 32 млн пикселей).");
            uint caps=U32(b,112);if((caps&0x200)!=0||(U32(b,24)>1))throw new InvalidDataException("Нужна двумерная текстура, не cubemap/volume DDS.");
            int offset=128,mode=0;uint flags=U32(b,80),four=U32(b,84);bool rawBgra=false,rawRgba=false;
            if((flags&4)!=0){if(four==0x31545844)mode=1;else if(four==0x33545844)mode=3;else if(four==0x35545844)mode=5;else if(four==0x30315844){if(b.Length<148)throw new InvalidDataException("DDS DX10 обрезан.");uint format=U32(b,128);if(U32(b,132)!=3||U32(b,140)!=1)throw new InvalidDataException("DDS array/3D не поддерживается.");offset=148;
                    if(format==71||format==72)mode=1;else if(format==74||format==75)mode=3;else if(format==77||format==78)mode=5;else if(format==28||format==29)rawRgba=true;else if(format==87||format==91)rawBgra=true;else throw new InvalidDataException("DDS DXGI "+format+" не поддерживается. Доступны BC1/2/3 и RGBA8.");}
                else throw new InvalidDataException("DDS FourCC не поддерживается. Доступны DXT1, DXT3, DXT5 и RGB(A).");}
            int[] pixels=new int[w*h];
            if(mode!=0){int bw=(w+3)/4,bh=(h+3)/4,size=mode==1?8:16;if((long)offset+(long)bw*bh*size>b.Length)throw new InvalidDataException("Недостаточно данных в DDS.");
                for(int by=0;by<bh;by++)for(int bx=0;bx<bw;bx++){
                    int p=offset+(by*bw+bx)*size,cp=p+(mode==1?0:8);int c0=b[cp]|b[cp+1]<<8,c1=b[cp+2]|b[cp+3]<<8;int[] colours=new int[4];colours[0]=Rgb565(c0);colours[1]=Rgb565(c1);
                    bool transparent=mode==1&&c0<=c1;if(transparent){colours[2]=Mix(colours[0],colours[1],1,1,2);colours[3]=0;}else{colours[2]=Mix(colours[0],colours[1],2,1,3);colours[3]=Mix(colours[0],colours[1],1,2,3);}
                    uint codes=U32(b,cp+4);int[] alpha=new int[8];ulong bits=0;if(mode==5){alpha[0]=b[p];alpha[1]=b[p+1];if(alpha[0]>alpha[1]){for(int i=2;i<8;i++)alpha[i]=((8-i)*alpha[0]+(i-1)*alpha[1])/7;}else{for(int i=2;i<6;i++)alpha[i]=((6-i)*alpha[0]+(i-1)*alpha[1])/5;alpha[6]=0;alpha[7]=255;}for(int i=0;i<6;i++)bits|=(ulong)b[p+2+i]<<(8*i);}
                    for(int i=0;i<16;i++){int x=bx*4+i%4,y=by*4+i/4;if(x>=w||y>=h)continue;int ci=(int)((codes>>(2*i))&3);int a=255;if(transparent&&ci==3)a=0;if(mode==3)a=((b[p+i/2]>>((i%2)*4))&15)*17;else if(mode==5)a=alpha[(int)((bits>>(3*i))&7)];pixels[y*w+x]=(a<<24)|colours[ci];}
                }
            }else {int bits=rawRgba||rawBgra?32:(int)U32(b,88);if(bits!=8&&bits!=16&&bits!=24&&bits!=32)throw new InvalidDataException("Поддерживаются A8, RGB16/24 и RGBA32 DDS.");int bytes=bits/8;uint rm=rawRgba?255:rawBgra?0xff0000:U32(b,92),gm=rawRgba||rawBgra?0xff00:U32(b,96),bm=rawRgba?0xff0000:rawBgra?255:U32(b,100),am=rawRgba||rawBgra?0xff000000:U32(b,104);
                int stride=w*bytes;if((U32(b,8)&8)!=0&&(int)U32(b,20)>=stride)stride=(int)U32(b,20);if((long)offset+(long)stride*h>b.Length)throw new InvalidDataException("Недостаточно RGB данных DDS.");
                for(int y=0;y<h;y++)for(int x=0;x<w;x++){int p=offset+y*stride+x*bytes;uint v=0;for(int j=0;j<bytes;j++)v|=(uint)b[p+j]<<(8*j);int fallback=(flags&2)!=0?255:0;pixels[y*w+x]=(Channel(v,am,255)<<24)|(Channel(v,rm,fallback)<<16)|(Channel(v,gm,fallback)<<8)|Channel(v,bm,fallback);}
            }
            Bitmap bitmap=new Bitmap(w,h,PixelFormat.Format32bppArgb);var data=bitmap.LockBits(new Rectangle(0,0,w,h),ImageLockMode.WriteOnly,PixelFormat.Format32bppArgb);try{for(int y=0;y<h;y++)Marshal.Copy(pixels,y*w,new IntPtr(data.Scan0.ToInt64()+y*data.Stride),w);}finally{bitmap.UnlockBits(data);}return bitmap;
        }
    }
}
