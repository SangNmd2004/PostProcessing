"""Exact large Hankel reference using integer NTT, not floating-point FFT.

Convolution coefficients are <= input length < modulus; reducing their exact
integer value modulo two therefore gives the GF(2) product. Public test data.
"""
import numpy as np

MOD=2013265921
ROOT=31

def _ntt(a,inverse=False):
    n=len(a)
    if n<1 or n&(n-1) or n>(1<<27):raise ValueError('unsupported transform size')
    idx=np.arange(n,dtype=np.uint32);rev=np.zeros(n,dtype=np.uint32)
    for _ in range(n.bit_length()-1):rev=(rev<<1)|(idx&1);idx>>=1
    a=a[rev].copy()
    length=2
    while length<=n:
        half=length//2
        wbase=pow(ROOT,(MOD-1)//length,MOD)
        if inverse:wbase=pow(wbase,MOD-2,MOD)
        def powers():
            w=1
            for _ in range(half):yield w;w=w*wbase%MOD
        w=np.fromiter(powers(),dtype=np.int64,count=half)
        blocks=a.reshape(-1,length);u=blocks[:,:half].copy()
        v=blocks[:,half:]*w%MOD
        blocks[:,:half]=(u+v)%MOD;blocks[:,half:]=(u-v)%MOD
        length*=2
    if inverse:a=a*pow(n,MOD-2,MOD)%MOD
    return a

def hankel_hash(x,seed,output_bits):
    x=np.asarray(x,dtype=np.uint8);seed=np.asarray(seed,dtype=np.uint8)
    if output_bits<1 or len(seed)<len(x)+output_bits-1 or len(x)>=MOD:
        raise ValueError('invalid dimensions')
    if np.any(x>1) or np.any(seed>1):raise ValueError('expected binary data')
    used=len(x)+output_bits-1
    n=1<<(len(x)+used-2).bit_length()
    a=np.zeros(n,dtype=np.int64);b=np.zeros(n,dtype=np.int64)
    a[:len(x)]=x[::-1];b[:used]=seed[:used]
    a=_ntt(a);b=_ntt(b)
    c=_ntt(a*b%MOD,True)
    return (c[len(x)-1:len(x)-1+output_bits]&1).astype(np.uint8)

if __name__=='__main__':
    import pa_model
    rng=np.random.default_rng(20261026)
    for size in [1,7,32,65,2765,4096]:
        for out in [1,64,1024]:
            x=rng.integers(0,2,size,dtype=np.uint8);s=rng.integers(0,2,size+out+32,dtype=np.uint8)
            assert np.array_equal(hankel_hash(x,s,out),pa_model.pa_hash(x,s,out))
    print('HANKEL_EXACT_NTT_REFERENCE_PASS 18 sizes')
