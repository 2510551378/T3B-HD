#include "T3BGEOriginalMatrix.h"
#include <cmath>
#include <stdexcept>
namespace {
void Check(bool v,const char* s){if(!v)throw std::runtime_error(s);}
float F32(float x){volatile float y=x;return y;}
void Valid(const T3BGE::OriginalMatrixInput& x){
    Check(std::isfinite(x.scalar)&&x.scalar!=0.f,"Invalid original matrix scalar");
    for(float v:x.p30)Check(std::isfinite(v),"Invalid original P+30 scale");
    for(const auto* m:{&x.input,&x.parent,&x.global})for(float v:*m)Check(std::isfinite(v),"Nonfinite original matrix input");
}
T3BGE::OriginalMatrix16 Multiply(const T3BGE::OriginalMatrix16& a,const T3BGE::OriginalMatrix16& b){
    T3BGE::OriginalMatrix16 out{};
    for(unsigned c=0;c<4;++c){
        for(unsigned r=0;r<4;++r){
            float sum=0.f;
            for(unsigned k=0;k<4;++k){sum=F32(sum+F32(a[k*4+r]*b[c*4+k]));}
            out[c*4+r]=sum;
        }
    }
    return out;
}
}
namespace T3BGE {
OriginalMatrix16 ComputeOriginalMatrixMode0(const OriginalMatrixInput& x){
    Valid(x);auto scaled=x.input;
    if(x.scalar!=1.f)for(unsigned c=0;c<3;++c)for(unsigned r=0;r<4;++r)scaled[c*4+r]=F32(scaled[c*4+r]*x.scalar);
    return Multiply(x.parent,scaled);
}
OriginalMatrix16 ComputeOriginalMatrixMode1(const OriginalMatrixInput& x){
    Valid(x);OriginalMatrix16 out{};
    for(unsigned c=0;c<3;++c)for(unsigned r=0;r<3;++r){float sum=0.f;for(unsigned k=0;k<3;++k){const float scaled=F32(F32(x.input[c*4+k]*x.scalar)*x.p30[c]);sum=F32(sum+F32(x.global[k*4+r]*scaled));}out[c*4+r]=sum;}
    for(unsigned r=0;r<4;++r){float sum=0.f;for(unsigned k=0;k<4;++k)sum=F32(sum+F32(x.parent[k*4+r]*x.input[3*4+k]));out[3*4+r]=sum;}
    out[3]=out[7]=out[11]=0.f;return out;
}
OriginalMatrix16 ComputeOriginalMatrix(const OriginalMatrixInput& x){
    if(x.mode==0){return ComputeOriginalMatrixMode0(x);}
    if(x.mode==1){return ComputeOriginalMatrixMode1(x);}
    throw std::runtime_error("Original matrix mode is not covered");
}
} // namespace T3BGE
