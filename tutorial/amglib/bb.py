import numpy as np
import matplotlib.pyplot as plt
from skimage.measure import label, regionprops
import skimage.io as io
import skimage.filters as filt
import skimage.morphology as morph
from skimage.draw import disk
import amglib.imageutils as amg
import pandas as pd
from skimage.feature import match_template

def get_dot_template(img, roi,se=morph.disk(5)) :
    """
    Extracts sub image from the region given by a ROI
    
    Parameters
    ----------
    img : ndarray (2D)
        The source image
    roi : array
        Region of interest to extract. Organized as (x0,y0,x1,y1)
    se  : ndarray (2D)
        Structure element for the median filter used to remove outliers from the template.
    

    Returns
    -------
    ndarray (2D)
        The template image

    """
    template=filt.median(img[roi[0]:roi[2],roi[1]:roi[3]],se)
    
    return template

def get_black_bodies(img, greythres,areas = [2000,4000],R=2) :
    bb=img<greythres
    lbb=label(bb)
    
    plt.imshow(bb)

    mask = np.zeros(lbb.shape)
    regions=[]

    for region in regionprops(lbb):
        if (region.area<areas[0]) or (areas[1]<region.area) :
            lbb[lbb==region.label]=0
        else:
            
            #regions.append(region)
            x,y = region.centroid
            rr, cc = disk((x,y), R)
            mask[rr, cc] = 255  
            dotdata = img[rr,cc]
            regions.append({'label': region.label,
                            'mean' : np.mean(dotdata),
                            'median' : np.median(dotdata),
                            'r' : region.centroid[0],
                            'c' : region.centroid[1]})

    mask=mask.astype('uint8')
    r,c = np.where(0<mask)
    df = pd.DataFrame.from_dict(regions)
    
    return mask,r,c,df

def get_blackbodies_by_templatematching(img,template,threshold,R=10) :
    """
    Finds the black body dots in a image using template matching.
    
    Parameters
    ----------
    img      : ndarray (2D)
    template : ndarray (2D)
    threshold : float
    R : int
    
    Returns
    -------
    ndarray (2D)
        A bilevel mask image marking out the bb dots with a standard radius given by R.
    ndarray (1D)
        row coordinates of the dot pixels
    ndarray (1D)
        column coordinates of the dot pixels
    pandas data frame
        Data frame containing the information about the detected dots 
    
    """
    tm = match_template(img, template,pad_input=True)
    lbb=label(threshold<tm)
    mask = np.zeros(lbb.shape)
    regions=[]

    area=(template<filt.threshold_otsu(template)).sum()
    areas = [0.2*area, 0.8*area]
    
    for region in regionprops(lbb):
        if (region.area<areas[0]) or (areas[1]<region.area) :
            lbb[lbb==region.label]=0
        else:
            x,y = region.centroid
            rr, cc = disk((x,y), R)
            mask[rr, cc] = 255  
            dotdata = img[rr,cc]
            regions.append({'label': region.label,
                            'mean' : np.mean(dotdata),
                            'median' : np.median(dotdata),
                            'r' : region.centroid[0],
                            'c' : region.centroid[1]})

    mask=mask.astype('uint8')
    r,c = np.where(0<mask)
    df = pd.DataFrame.from_dict(regions)
    
    return mask,r,c,df,tm


def compute_scatter_image(img,r,c) :
    y = img[r,c]

    H=np.transpose([r,c,r**2,c**2,r*c])
    H=np.concatenate((np.ones([H.shape[0],1]),H),axis=1)

    q=np.linalg.lstsq(H, y, rcond=None)

    res=polynomial_image(img.shape,q[0])
    return res

def compute_scatter_image_from_df(df,shape,info='median') :
    
    y = df[info]
    H=np.transpose([df['r'],df['c'],df['r']**2,df['c']**2,df['r']*df['c']])
    H=np.concatenate((np.ones([H.shape[0],1]),H),axis=1)
    
    q=np.linalg.lstsq(H, y, rcond=None)

    res=polynomial_image(shape,q[0])
    
    return res

def polynomial_image(size,q) :
    c,r = np.meshgrid(np.arange(size[1]),np.arange(size[0]))

    img = np.ones(size)*q[0]
    img = img + r*q[1]
    img = img + c*q[2]
    img = img + r**2*q[3]
    img = img + c**2*q[4]
    img = img + r*c*q[5]

    return img

def check_scatter_image(bb, est,  mask, areas=[100,1000], show=True, ax=None, cmap='jet', sym_cmap=False, clim = [0,10000]) :   
    lbb=label(mask)

    diff = bb - est 
    
    regdata = []
    
    for region in regionprops(lbb):
        if (region.area<areas[0]) or (areas[1]<region.area) :
            lbb[lbb==region.label]=0
        else:
            x,y = region.centroid
            
            med   = np.median(diff[lbb==region.label])
            mean  = diff[lbb==region.label].mean()
            mse   = (diff**2)[lbb==region.label].mean()
            
            regdata.append({'label':  region.label, 
                            'Median': med, 
                            'Mean':   mean, 
                            'MSE':    mse, 
                            'RMSE':   np.sqrt(mse),
                            'area':   region.area, 
                            'centroid': region.centroid, 
                            'x':      y, 
                            'y':      x})
    
    df=pd.DataFrame.from_dict(regdata)
    
    if show :
        if ax is None :
            fig,ax =plt.subplots(1,1,figsize=(10,10))
            
        ax.imshow(bb,vmin=clim[0],vmax=clim[1],cmap='gray')
        
        if sym_cmap :
            v = np.max([np.abs(df['Median'].max()),np.abs(df['Median'].min())])
            a=ax.scatter(df['x'],df['y'],c=df['Median'],vmin=-v,vmax=v,cmap=cmap)
        else :
            a=ax.scatter(df['x'],df['y'],c=df['Median'],cmap=cmap)
            
        plt.gcf().colorbar(a,ax=ax,shrink=0.5)
    
    return df

def normalize(img,ob,dc, dose_roi=None,logarithm=True) :
    img=img-dc
    img[img<1]=1
    ob=ob-dc
    ob[ob<1]=1
    
    D=1
    
    if dose_roi is not None:
        dob=ob[dose_roi[0]:dose_roi[2],dose_roi[1]:dose_roi[3]]
        dimg=img[dose_roi[0]:dose_roi[2],dose_roi[1]:dose_roi[3]]
        D=np.median(dob,axis=0).mean()/np.median(dimg,axis=0).mean()
        
    n=D*img/ob
    
    if logarithm :
        n=-np.log(n)
        
    return n

def remove_dc(img,dc) : 
    if dc != 0 :
        img = img - dc
        img[img<1]=1
    return img

def D(img, roi) :
    return np.median(img[roi[0]:roi[2],roi[1]:roi[3]],axis=0).mean()

def normalization_with_BB(sample,ob,dc,bbsample,bbob,ssample,sob,roi,tau) :
    sample   = remove_dc(sample,dc)
    ob       = remove_dc(ob,dc)
    bbsample = remove_dc(bbsample,dc)
    bbob     = remove_dc(bbob,dc)
    
    dsample   = D(sample,roi)
    dob       = D(ob,roi)
    dbbsample = D(bbsample,roi)
    dbbob     = D(bbob,roi)
    dssample  = D(ssample,roi)
    dsob      = D(sob,roi)
    
    ds = (dsample/(tau*(dbbsample-(1-1/tau)*dssample)))
    do = (dob/(tau*(dbbob-(1-1/tau)*dsob)))
    corrected = (sample - ssample*ds)/(ob - sob*do) * (do/ds)
    
    return corrected
    